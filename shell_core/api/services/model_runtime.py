"""model_runtime.py — local-model (Ollama) runtime control.

The chat dispatcher loads local models on demand; Ollama then keeps each
one resident for OLLAMA_KEEP_ALIVE after its last turn. When a chat
session switches off a local model, that residency is pure waste — the
warm prefix cache it protects belongs to a model the session no longer
talks to. `unload_if_local` evicts it.

Best-effort by design: an unload failure — Ollama down, model already
gone — must never fail the switch request that triggered it.
"""
from __future__ import annotations

import json
import sqlite3
import urllib.request

_DEFAULT_OLLAMA_BASE = "http://localhost:11434"


def _ollama_base(endpoint: str | None) -> str:
    """The native Ollama API base for a model's registry `endpoint`.
    Mirrors ollama_adapter.py: a trailing `/v1` (OpenAI-compat URL) is
    tolerated — the native API lives at the bare base."""
    base = (endpoint or _DEFAULT_OLLAMA_BASE).rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3].rstrip("/")
    return base


def _ollama_call(url: str, body: dict | None, timeout: float) -> dict:
    """One Ollama HTTP call — POST when `body` is given, else GET."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method="POST" if data is not None else "GET",
        headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def unload_if_local(con: sqlite3.Connection, model_id) -> bool:
    """Evict `model_id` from Ollama if it is a local model and currently
    resident. Returns True when an unload was sent.

    Best-effort: every failure is swallowed — unloading is an
    optimization, never a reason to fail the caller's switch request. The
    `/api/ps` check first means an absent model is left alone, so this
    never loads a model just to evict it.
    """
    if not model_id:
        return False
    row = con.execute(
        "SELECT name, provider, endpoint FROM models WHERE model_id=?",
        (model_id,),
    ).fetchone()
    if row is None or row["provider"] != "local":
        return False
    base, name = _ollama_base(row["endpoint"]), row["name"]
    try:
        ps = _ollama_call(base + "/api/ps", None, timeout=3)
        if name not in {m.get("name") for m in (ps.get("models") or [])}:
            return False
        # keep_alive=0 with empty messages: Ollama evicts the model now.
        _ollama_call(base + "/api/chat",
                     {"model": name, "messages": [], "keep_alive": 0}, 10)
        return True
    except Exception:
        return False  # best-effort — never break the caller
