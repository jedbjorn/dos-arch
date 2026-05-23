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
    python3 shell_core/scripts/model_sync.py --watch [--interval SECONDS]

`--watch` runs continuously, re-syncing whenever Ollama's installed-model
set changes (a pull or an rm). dos-arch runs it this way as the
`dosarch-modelsync` pm2 process, so the registry tracks Ollama hands-free.

Env:
    OLLAMA_HOST           override the Ollama endpoint (default 127.0.0.1:11434)
    MODEL_WATCH_INTERVAL  --watch poll interval in seconds (default 30)
"""
import argparse
import json
import os
import re
import socket
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "shell_core" / "shell_db.db"

VRAM_TIERS = [8, 12, 24, 32, 48, 128]
VRAM_HEADROOM_GB = 1.5  # KV cache + runtime overhead on top of weights

# ── Template classifier ──────────────────────────────────────────────────────
#
# Some Ollama templates (hermes3-class) emit user-supplied System content only
# in the *else* branch of a `.Tools` conditional — when the dispatcher passes
# tools, those templates silently drop the substrate boot prompt before the
# model sees it. We detect that pattern by static regex over the template
# string from /api/show; no canary probe, no model load.
#
# The regex is whitespace-tolerant and matches the canonical Go-template
# shape used by hermes3:
#   {{- if .Tools }} … {{- else if .System }} … {{- end }}
# False-positive risk (a template that has *another* System branch elsewhere
# in the file) exists but is small in practice. The UI carries a manual
# "Move to agents" toggle as the safety net for any pattern we don't catch.
_DROPS_SYSTEM_RE = re.compile(
    r"\{\{-?\s*if\s+\.Tools\s*\}\}.*?"
    r"\{\{-?\s*else\s+if\s+\.System\s*\}\}",
    re.DOTALL,
)


def _bool_to_int(v: bool | None) -> int | None:
    """SQLite stores classification flags as 1/0/NULL — keep None passing
    through so an unknown classification lands as NULL, not 0."""
    return None if v is None else (1 if v else 0)


def _accepts_substrate_system(template: str | None) -> bool | None:
    """Classify a template's stance on System + Tools. Returns True iff the
    template emits user-supplied System content unconditionally (or under
    Tools); False iff it drops System in the Tools branch (hermes-class).
    Returns None when the template string is missing — that's "unknown",
    written to the DB as NULL so the classifier re-evaluates next tick."""
    if not template:
        return None
    return _DROPS_SYSTEM_RE.search(template) is None


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
        # Per-name classification gathered from /api/show — used by
        # promote_local_models to populate models.supports_tools and
        # models.accepts_substrate_system. None means "unknown" → written
        # as NULL so the classifier retries next tick.
        classification: dict[str, dict[str, bool | None]] = {}
        inserted = updated = 0

        for m in models:
            name = m["name"]
            seen.append(name)
            details = m.get("details") or {}
            size_gb = round(m["size"] / 1024**3, 2) if m.get("size") else None

            show: dict | None
            try:
                show = _api(base, "/api/show", {"name": name})
            except (urllib.error.URLError, OSError):
                show = None
            if show is None:
                classification[name] = {"supports_tools": None,
                                        "accepts_substrate_system": None}
                show = {}
            else:
                classification[name] = {
                    "supports_tools": "tools" in (show.get("capabilities") or []),
                    "accepts_substrate_system":
                        _accepts_substrate_system(show.get("template")),
                }

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

        promoted, reactivated, deactivated = promote_local_models(
            con, hw_id, base, classification)
        con.commit()
    finally:
        con.close()

    print(f"installed_models (hardware_id={hw_id}): "
          f"{inserted} inserted, {updated} updated, {removed} marked removed.")
    print(f"models registry: {promoted} promoted, {reactivated} reactivated, "
          f"{deactivated} deactivated.")


def promote_local_models(
    con: sqlite3.Connection, hw_id: int, base: str,
    classification: dict[str, dict[str, bool | None]],
) -> tuple[int, int, int]:
    """Mirror this host's installed Ollama models into the `models` registry
    so they are dispatchable (CC-62). Each installed model becomes a
    provider='local' row whose `status` and classification flags reflect
    what /api/show told us:

      - `supports_tools=1` only when `capabilities` contains `"tools"`;
      - `accepts_substrate_system=1` only when the template doesn't drop
        user-supplied System under Tools (hermes-class is 0);
      - row goes `status='active'` iff *both* flags are 1; otherwise
        `inactive` (visible in the registry as a record of what was
        filtered, hidden from the picker, routable to the agent surface).

    A flag stays NULL when /api/show is unreachable for that model on this
    tick — the classifier retries on every watch tick that still finds a
    NULL, so a flaky probe self-heals. NULL classifications keep the row
    out of the picker (the API filter requires =1, not "not =0").

    Returns (promoted, reactivated, deactivated).
    """
    endpoint = base.rstrip("/")  # Ollama base URL — the adapter appends /api/chat
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
            "SELECT status, supports_tools, accepts_substrate_system "
            "FROM models WHERE name=?",
            (name,),
        ).fetchone()
        prior_status, prior_st, prior_as = (
            prior if prior is not None else (None, None, None)
        )

        cls = classification.get(name) or {}
        fresh_st = _bool_to_int(cls.get("supports_tools"))
        fresh_as = _bool_to_int(cls.get("accepts_substrate_system"))
        # Classifications are sticky once written — by the classifier OR by
        # the manual "Move to agents" UI. Fresh reads only fill in NULLs.
        # Without this, a user-set 0 would be overwritten back to 1 on the
        # next watch tick if the template regex disagreed.
        eff_st = prior_st if prior_st is not None else fresh_st
        eff_as = prior_as if prior_as is not None else fresh_as

        substrate_capable = eff_st == 1 and eff_as == 1
        target_status = "active" if substrate_capable else "inactive"
        # display_name and auth_ref are kept out of the UPDATE branch so a
        # human-tuned registry row keeps its label.
        con.execute(
            """
            INSERT INTO models
                (name, display_name, provider, endpoint, auth_ref,
                 tool_dialect, context_window, locality, vram_estimate_gb,
                 status, supports_tools, accepts_substrate_system)
            VALUES
                (:name, :display, 'local', :endpoint, NULL,
                 'openai', :ctx, 'local', :vram, :status,
                 :supports_tools, :accepts_substrate_system)
            ON CONFLICT(name) DO UPDATE SET
                provider='local', endpoint=excluded.endpoint,
                tool_dialect='openai', context_window=excluded.context_window,
                locality='local', vram_estimate_gb=excluded.vram_estimate_gb,
                status=excluded.status,
                supports_tools=excluded.supports_tools,
                accepts_substrate_system=excluded.accepts_substrate_system
            """,
            {"name": name, "display": f"{name} (local)", "endpoint": endpoint,
             "ctx": ctx, "vram": vram, "status": target_status,
             "supports_tools": eff_st,
             "accepts_substrate_system": eff_as},
        )
        if prior is None and substrate_capable:
            promoted += 1
        elif prior is not None and prior_status != "active" and substrate_capable:
            reactivated += 1

    # Down-sweep: any active local row whose model is no longer installed
    # gets flipped to inactive. Tool-incapable installed rows are already
    # inactive from the upsert above, so they don't need a separate sweep.
    placeholders = ",".join("?" * len(seen)) or "''"
    cur = con.execute(
        f"""UPDATE models SET status='inactive'
            WHERE provider='local' AND status='active'
              AND name NOT IN ({placeholders})""",
        seen,
    )
    return promoted, reactivated, cur.rowcount


def watch(db_path: Path, user_id: int, interval: int) -> None:
    """Re-sync whenever Ollama's installed-model set changes.

    A standing process (dos-arch runs it as the `dosarch-modelsync` pm2 app):
    every `interval` seconds it fetches `/api/tags` and compares a signature
    of (name, digest) pairs against the last seen. On any change — and on
    first start — it runs the full sync. A failure (Ollama down, no
    user_hardware row) is logged once, then retried each tick until it clears.
    """
    base = _ollama_base()
    print(f"model_sync watch: polling {base} every {interval}s", flush=True)
    last_sig: tuple | None = None
    last_err: str | None = None
    while True:
        err: str | None = None
        try:
            tags = _api(base, "/api/tags")
            sig = tuple(sorted(
                (m["name"], m.get("digest", "")) for m in tags.get("models", [])
            ))
            if sig != last_sig:
                print(f"model_sync watch: installed set changed "
                      f"({len(sig)} model(s)) — syncing", flush=True)
                sync(db_path, user_id)
                last_sig = sig
        except SystemExit as e:
            err = f"sync aborted: {e}"
        except (urllib.error.URLError, OSError) as e:
            err = f"Ollama unreachable: {e}"
        except Exception as e:                       # noqa: BLE001
            err = f"unexpected {type(e).__name__}: {e}"
        if err and err != last_err:
            print(f"model_sync watch: {err} — will retry", file=sys.stderr, flush=True)
        last_err = err
        time.sleep(interval)


def main() -> int:
    ap = argparse.ArgumentParser(description="Sync installed_models + the models registry from Ollama.")
    ap.add_argument("--user-id", type=int, default=1, help="owning user_id (default 1)")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB, help="path to shell_db.db")
    ap.add_argument("--watch", action="store_true",
                    help="run continuously, re-syncing when Ollama's installed set changes")
    try:
        default_interval = max(5, int(os.environ.get("MODEL_WATCH_INTERVAL", "30")))
    except ValueError:
        default_interval = 30
    ap.add_argument("--interval", type=int, default=default_interval,
                    help="--watch poll interval in seconds (default 30)")
    args = ap.parse_args()
    if args.watch:
        watch(args.db, args.user_id, args.interval)
    else:
        sync(args.db, args.user_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
