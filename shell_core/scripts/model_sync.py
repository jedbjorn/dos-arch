#!/usr/bin/env python3
"""model_sync — sync the installed_models table from Ollama's installed set.

Ground truth, like the dr_* catalogue: reads what is really installed via
the Ollama HTTP API (/api/tags + /api/show), resolves the host it is
running on to a user_hardware row, and UPSERTs one installed_models row per
model.
Models previously recorded for this host but no longer present are flipped
to status='removed' (the row is kept for history).

It then promotes the installed set into the `models` registry (CC-62): each
installed model becomes an active provider='local' row that the dispatcher
and the model-switch dropdown can use; a local registry row whose model is
no longer installed is flipped to status='inactive'. The registry tracks
Ollama on its own — nothing is hand-registered.

Machine-readable fields (size, params, quantization, context length,
digest) come straight from Ollama. The editorial bits — provider, our
family taxonomy, description — come from the small curated maps below;
unknown models still sync, just with those fields left NULL.

Requires a user_hardware row for this host first — run collect_hardware.py.

Usage:
    python3 shell_core/scripts/model_sync.py [--user-id N] [--db PATH]

Env:
    OLLAMA_HOST   override the Ollama endpoint (default 127.0.0.1:11434)
"""
import argparse
import json
import os
import socket
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "shell_core" / "shell_db.db"

VRAM_TIERS = [8, 12, 24, 32, 48, 128]
VRAM_HEADROOM_GB = 1.5  # KV cache + runtime overhead on top of weights

# name-prefix -> provider. First matching prefix wins.
_PROVIDER_MAP = [
    ("mistral", "Mistral"), ("mixtral", "Mistral"),
    ("codestral", "Mistral"), ("devstral", "Mistral"),
    ("qwen", "Alibaba"), ("llama", "Meta"), ("codellama", "Meta"),
    ("gemma", "Google"), ("phi", "Microsoft"),
    ("deepseek", "DeepSeek"), ("granite", "IBM"),
]

# base name (before the ':') -> (our family taxonomy, description_short <=100)
_MODEL_META = {
    "mistral":         ("general",   "Mistral's classic 7B — fast, solid general-purpose baseline."),
    "qwen2.5-coder":   ("coder",     "Alibaba's small coding model — strong at code edits and completion."),
    "qwen3":           ("general",   "Alibaba's newer general model with an optional thinking/reasoning mode."),
    "gemma3":          ("multimodal","Google's compact model — strong for its size, handles images."),
    "llama3.1":        ("general",   "Meta's reference general-purpose instruct model."),
    "llama3.2":        ("general",   "Meta's small general-purpose instruct model."),
    "llama3.3":        ("general",   "Meta's flagship 70B general-purpose instruct model."),
    "deepseek-r1":     ("reasoning", "DeepSeek distilled reasoning model — chain-of-thought output."),
    "phi4-mini":       ("general",   "Microsoft's small model — punchy reasoning for its size."),
    "phi4":            ("reasoning", "Microsoft's 14B reasoning-focused model."),
    "codestral":       ("coder",     "Mistral's dedicated code model."),
    "devstral":        ("coder",     "Mistral's agentic coding model (24B)."),
    "mistral-nemo":    ("general",   "Mistral + NVIDIA 12B — strong general-purpose model."),
    "mistral-small":   ("general",   "Mistral's 24B general-purpose model."),
}


def _ollama_base() -> str:
    host = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434").strip()
    if not host.startswith("http"):
        host = "http://" + host
    return host.rstrip("/")


def _api(base: str, path: str, payload: dict | None = None) -> dict:
    url = base + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _provider(name: str) -> str | None:
    low = name.lower()
    for prefix, prov in _PROVIDER_MAP:
        if low.startswith(prefix):
            return prov
    return None


def _min_vram_gb(size_gb: float | None) -> int | None:
    if size_gb is None:
        return None
    need = size_gb + VRAM_HEADROOM_GB
    for t in VRAM_TIERS:
        if t >= need:
            return t
    return VRAM_TIERS[-1]  # bigger than the largest tier — flag the top tier


def _context_length(show: dict) -> int | None:
    info = show.get("model_info") or {}
    for key, val in info.items():
        if key.endswith(".context_length"):
            try:
                return int(val)
            except (TypeError, ValueError):
                return None
    return None


def resolve_hardware_id(con: sqlite3.Connection, user_id: int) -> int:
    hostname = socket.gethostname()
    row = con.execute(
        "SELECT hardware_id FROM user_hardware WHERE user_id=? AND hostname=?",
        (user_id, hostname),
    ).fetchone()
    if not row:
        sys.exit(
            f"error: no user_hardware row for host '{hostname}' (user_id={user_id}).\n"
            f"       run: python3 shell_core/scripts/collect_hardware.py --user-id {user_id}"
        )
    return row[0]


def sync(db_path: Path, user_id: int) -> None:
    base = _ollama_base()
    try:
        tags = _api(base, "/api/tags")
    except (urllib.error.URLError, OSError) as e:
        sys.exit(f"error: cannot reach Ollama at {base} ({e}).\n"
                 f"       is the service running?  systemctl status ollama")

    models = tags.get("models", [])
    con = sqlite3.connect(db_path)
    try:
        hw_id = resolve_hardware_id(con, user_id)
        seen: list[str] = []
        inserted = updated = 0

        for m in models:
            name = m["name"]
            seen.append(name)
            details = m.get("details") or {}
            size_gb = round(m["size"] / 1024**3, 2) if m.get("size") else None

            try:
                show = _api(base, "/api/show", {"name": name})
            except (urllib.error.URLError, OSError):
                show = {}

            rec = {
                "hardware_id": hw_id,
                "name": name,
                "runner": "ollama",
                "provider": _provider(name),
                "family": _MODEL_META.get(name.split(":")[0], (None, None))[0]
                          or details.get("family"),
                "params": details.get("parameter_size"),
                "size_gb": size_gb,
                "quantization": details.get("quantization_level"),
                "context_length": _context_length(show),
                "min_vram_gb": _min_vram_gb(size_gb),
                "digest": (m.get("digest") or "")[:12] or None,
                "description_short": _MODEL_META.get(name.split(":")[0], (None, None))[1],
            }

            exists = con.execute(
                "SELECT 1 FROM installed_models WHERE hardware_id=? AND name=?",
                (hw_id, name),
            ).fetchone()
            con.execute(
                """
                INSERT INTO installed_models
                    (hardware_id, name, runner, provider, family, params,
                     size_gb, quantization, context_length, min_vram_gb,
                     digest, status, description_short, last_synced)
                VALUES
                    (:hardware_id, :name, :runner, :provider, :family, :params,
                     :size_gb, :quantization, :context_length, :min_vram_gb,
                     :digest, 'installed', :description_short, datetime('now'))
                ON CONFLICT(hardware_id, name) DO UPDATE SET
                    runner=excluded.runner, provider=excluded.provider,
                    family=excluded.family, params=excluded.params,
                    size_gb=excluded.size_gb, quantization=excluded.quantization,
                    context_length=excluded.context_length,
                    min_vram_gb=excluded.min_vram_gb, digest=excluded.digest,
                    status='installed', description_short=excluded.description_short,
                    last_synced=datetime('now')
                """,
                rec,
            )
            if exists:
                updated += 1
            else:
                inserted += 1

        # Models recorded for this host but no longer installed -> removed.
        placeholders = ",".join("?" * len(seen)) or "''"
        cur = con.execute(
            f"""UPDATE installed_models SET status='removed', last_synced=datetime('now')
                WHERE hardware_id=? AND status='installed'
                  AND name NOT IN ({placeholders})""",
            (hw_id, *seen),
        )
        removed = cur.rowcount

        promoted, reactivated, deactivated = promote_local_models(con, hw_id, base)
        con.commit()
    finally:
        con.close()

    print(f"installed_models (hardware_id={hw_id}): "
          f"{inserted} inserted, {updated} updated, {removed} marked removed.")
    print(f"models registry: {promoted} promoted, {reactivated} reactivated, "
          f"{deactivated} deactivated.")


def promote_local_models(con: sqlite3.Connection, hw_id: int,
                         base: str) -> tuple[int, int, int]:
    """Mirror this host's installed Ollama models into the `models` registry
    so they are dispatchable (CC-62). Each installed model becomes an active
    provider='local' row; a local registry row whose model is no longer
    installed is flipped to status='inactive' (kept for history, FK-safe).

    Single Ollama host is assumed — the down-sweep reconciles every
    provider='local' row against this host's installed set. Scope this by
    endpoint/hardware if a second Ollama host is ever added.

    Returns (promoted, reactivated, deactivated).
    """
    endpoint = base.rstrip("/") + "/v1"  # Ollama's OpenAI-compatible base URL
    installed = con.execute(
        "SELECT name, context_length, min_vram_gb FROM installed_models "
        "WHERE hardware_id=? AND status='installed'",
        (hw_id,),
    ).fetchall()

    seen: list[str] = []
    promoted = reactivated = 0
    for name, ctx, vram in installed:
        seen.append(name)
        prior = con.execute(
            "SELECT status FROM models WHERE name=?", (name,)
        ).fetchone()
        # display_name and auth_ref are kept out of the UPDATE branch so a
        # human-tuned registry row keeps its label.
        con.execute(
            """
            INSERT INTO models
                (name, display_name, provider, endpoint, auth_ref,
                 tool_dialect, context_window, locality, vram_estimate_gb,
                 status)
            VALUES
                (:name, :display, 'local', :endpoint, NULL,
                 'openai', :ctx, 'local', :vram, 'active')
            ON CONFLICT(name) DO UPDATE SET
                provider='local', endpoint=excluded.endpoint,
                tool_dialect='openai', context_window=excluded.context_window,
                locality='local', vram_estimate_gb=excluded.vram_estimate_gb,
                status='active'
            """,
            {"name": name, "display": f"{name} (local)", "endpoint": endpoint,
             "ctx": ctx, "vram": vram},
        )
        if prior is None:
            promoted += 1
        elif prior[0] != "active":
            reactivated += 1

    placeholders = ",".join("?" * len(seen)) or "''"
    cur = con.execute(
        f"""UPDATE models SET status='inactive'
            WHERE provider='local' AND status='active'
              AND name NOT IN ({placeholders})""",
        seen,
    )
    return promoted, reactivated, cur.rowcount


def main() -> int:
    ap = argparse.ArgumentParser(description="Sync installed_models + the models registry from Ollama.")
    ap.add_argument("--user-id", type=int, default=1, help="owning user_id (default 1)")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB, help="path to shell_db.db")
    args = ap.parse_args()
    sync(args.db, args.user_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
