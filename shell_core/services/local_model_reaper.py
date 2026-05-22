"""local_model_reaper.py — sweep orphaned local models out of Ollama.

The dispatcher loads local models on demand; Ollama then keeps each one
resident for OLLAMA_KEEP_ALIVE after its last turn. Cleared sessions
still reference their model_id (so a returning user pays no reload cost),
but a *switch* rewrites the session's model_id — at which point no row
references the old local model and its residency is pure waste.

This sweep enforces the invariant: a resident local model with no
chat_session referencing its model_id is orphaned and should be evicted.

Lives in the dispatcher (host-side) because the substrate API runs in a
container with no route to host Ollama. A "best-effort" unload from the
API silently fails — this one actually runs.

Switch vs. clear semantics fall out naturally from the consumer rule:
  - switch: update_session rewrites chat_sessions.model_id, the old row
    drops out of the consumer set, sweep unloads on the next tick.
  - clear:  clear_session sets is_active=0 but leaves model_id intact,
    so the cleared row still counts as a consumer; Ollama's own
    keep_alive expires it eventually.

Best-effort by design: every Ollama call is wrapped — a down endpoint or
a model already evicted must never crash the dispatcher.
"""
from __future__ import annotations

import json
import sys
import threading
import urllib.request
from collections import defaultdict

_DEFAULT_BASE = "http://localhost:11434"


def _ollama_base(endpoint: str | None) -> str:
    """The native Ollama API base for a model's `endpoint`.
    Mirrors ollama_adapter.py: a trailing `/v1` (OpenAI-compat URL) is
    tolerated — the native API lives at the bare base."""
    base = (endpoint or _DEFAULT_BASE).rstrip("/")
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


def _orphan_local_models(con) -> list:
    """Local models with no chat_session referencing them. Cleared sessions
    keep their model_id, so the model stays warm until Ollama's keep_alive
    expires; a switch rewrites the session's model_id, dropping the row
    from this set and making the model eligible for eviction."""
    return con.execute(
        "SELECT m.model_id, m.name, m.endpoint "
        "FROM models m "
        "WHERE m.provider='local' "
        "AND NOT EXISTS ("
        "  SELECT 1 FROM chat_sessions cs WHERE cs.model_id = m.model_id"
        ")"
    ).fetchall()


def reap_once(con) -> list[str]:
    """One sweep: unload every orphan local model that is currently
    resident in Ollama. Returns the list of unloaded model names.

    Per-base failures (Ollama down, transient network error) are
    swallowed — the next sweep retries. One `/api/ps` call per Ollama
    base, not per model: cheap when many local models share an endpoint."""
    orphans = _orphan_local_models(con)
    if not orphans:
        return []

    by_base: dict[str, list[str]] = defaultdict(list)
    for row in orphans:
        by_base[_ollama_base(row["endpoint"])].append(row["name"])

    unloaded: list[str] = []
    for base, names in by_base.items():
        try:
            ps = _ollama_call(base + "/api/ps", None, 3)
            resident = {m.get("name") for m in (ps.get("models") or [])}
        except Exception:
            continue
        for name in names:
            if name not in resident:
                continue
            try:
                # keep_alive=0 with empty messages: Ollama evicts now.
                _ollama_call(base + "/api/chat",
                             {"model": name, "messages": [], "keep_alive": 0}, 10)
                unloaded.append(name)
            except Exception:
                pass
    return unloaded


def reaper_loop(db_factory, stop_event: threading.Event, sweep_sec: float) -> None:
    """Run `reap_once` every `sweep_sec` until `stop_event` is set.
    `db_factory` is a callable returning a fresh sqlite3 Connection —
    we open + close per sweep, no long-lived handle."""
    while not stop_event.is_set():
        try:
            con = db_factory()
            try:
                unloaded = reap_once(con)
            finally:
                con.close()
            if unloaded:
                print(f"local-model reaper: unloaded {unloaded}", flush=True)
        except Exception as e:
            print(f"local-model reaper error: {e}", file=sys.stderr, flush=True)
        stop_event.wait(sweep_sec)
