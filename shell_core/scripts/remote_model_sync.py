#!/usr/bin/env python3
"""remote_model_sync — sync the `models` registry with the first-party remote
provider catalogs (Anthropic, OpenAI).

Companion to `cloud_model_sync.py` (Ollama Cloud) and `model_sync.py` (local
Ollama). Those two providers self-update because something polls a catalog;
the first-party SDK providers had no such loop — their rows were a hardcoded
seed in `db_init.py` that only ran at fresh bootstrap, so a new Opus/GPT
release stayed invisible until someone hand-edited the seed and shipped a
migration. This script closes that asymmetry: it reads each provider's
`/v1/models` listing and UPSERTs one row per model the provider serves.

Unlike Ollama Cloud's anonymous `/api/tags`, these listings REQUIRE the
provider API key. The read runs in one of two modes, resolved per call:

  - Broker mode (BROKER_BASE set — the credential-free API container): the
    request goes to the broker's per-provider prefix
    (http://dos-broker:8788/<provider>/v1/models) carrying NO key; the broker
    injects it on egress. No provider key is ever present in this process.
  - Direct mode (host CLI/cron): the request goes straight to the provider
    with the key from the environment (`ANTHROPIC_API_KEY`/`OPENAI_API_KEY`),
    falling back to ~/.config/dos-arch/.env so the CLI and cron work host-side
    without ceremony. A provider whose key is absent is skipped cleanly — its
    rows are left untouched (no fetch, no down-sweep), so a missing key never
    silently disables a working catalog.

Per-provider policy differs because the catalogs differ:
  - Anthropic: every row is a chat model with a short id matching our naming
    convention and a provider-supplied display_name. Take all; labels free.
  - OpenAI: a ~120-row firehose mixing embeddings, audio, image, realtime,
    moderation, and a dated snapshot for nearly every alias, with no
    display_name field. We allowlist the chat-capable text families, drop the
    non-text variants, collapse dated snapshots onto their bare alias, and
    synthesize a display_name.

New rows land `status='inactive'`: the per-provider config pages
(/anthropicconfig, /openaiconfig) are the opt-in surface, mirroring
/ollamacloudconfig. On conflict the upsert PRESERVES `status` — a row a user
activated (or deactivated, e.g. retiring an old model) keeps that choice
across refreshes. `last_verified` is set on every successful upsert and gates
the down-sweep: a previously-synced row absent from the latest listing is
flipped inactive; hand-seeded rows (`last_verified IS NULL`) are exempt until
their first sync, so the bootstrap default-active set survives a key-less run.

Usage:
    python3 shell_core/scripts/remote_model_sync.py [--provider anthropic|openai] [--db PATH]

Env:
    BROKER_BASE                          if set, route reads through the broker
                                         (credential-free); else direct mode
    ANTHROPIC_API_KEY / OPENAI_API_KEY   per-provider catalog auth (direct mode)
    ANTHROPIC_BASE / OPENAI_BASE         override the API base (direct, testing)
"""
import argparse
import json
import os
import re
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT       = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "shell_core" / "shell_db.db"
ENV_FILE   = Path.home() / ".config" / "dos-arch" / ".env"

_ANTHROPIC_VERSION = "2023-06-01"
_TIMEOUT           = 30

# ── OpenAI catalog policy ─────────────────────────────────────────────────────
# The /v1/models listing returns every model the account can touch. We keep the
# chat-capable text families and drop everything else by name.
#
# ALLOW: a name must START with one of these to be considered at all. The
# o-series reasoning models (o1/o3/o4) carry no `gpt-` prefix, hence the
# separate `o\d` rule.
_OPENAI_ALLOW = re.compile(r"^(gpt-4o|gpt-4\.1|gpt-5|o\d)")
# DENY: even within an allowed family, these substrings mark a non-text or
# non-chat modality (or a retrieval-augmented variant that isn't a plain chat
# model). A name matching any of these is dropped.
_OPENAI_DENY = re.compile(
    r"(audio|realtime|transcribe|tts|whisper|image|search|moderation|embedding|sora|dall-e)"
)
# A trailing ISO date marks a pinned snapshot (gpt-5.5-2026-04-23). When the
# bare alias (gpt-5.5) is also present we keep the alias and drop the snapshot.
_OPENAI_SNAPSHOT = re.compile(r"^(?P<base>.+)-\d{4}-\d{2}-\d{2}$")


class CatalogFetchError(RuntimeError):
    """A provider /v1/models read failed — network error, HTTP error, bad
    payload, or (caller's choice to raise) a missing API key. The CLI prints
    and exits non-zero; the API endpoint catches it and returns 502."""


class MissingKeyError(RuntimeError):
    """The provider's API key is not set in the environment. Distinct from
    CatalogFetchError so callers can skip the provider rather than fail."""


def _load_env_file() -> None:
    """Populate os.environ from ~/.config/dos-arch/.env for any key not already
    set. Mirrors ecosystem.config.cjs's loadEnv so the CLI + cron pick up the
    operator's secrets host-side without an explicit `source`. Absent file is
    fine — the provider just gets skipped if its key never materializes."""
    try:
        for line in ENV_FILE.read_text().splitlines():
            m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$", line)
            if not m:
                continue
            name, val = m.group(1), m.group(2)
            val = re.sub(r"^(['\"])(.*)\1$", r"\2", val)
            os.environ.setdefault(name, val)
    except OSError:
        pass


def _http_get_json(url: str, headers: dict) -> dict:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise CatalogFetchError(
            f"HTTP {e.code} from {url}: "
            f"{e.read().decode(errors='replace')[:200]}") from e
    except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
        raise CatalogFetchError(f"unreachable {url}: {e}") from e


# ── Anthropic ─────────────────────────────────────────────────────────────────

def _fetch_anthropic(base: str, headers: dict) -> list[dict]:
    """GET /v1/models, following pagination. Returns normalized rows:
    {name, display_name, context_window, source_url}. Anthropic gives short
    ids that already match our naming and a display_name per model; no
    context_window in the payload, so we stamp a flat 200k (every current
    Claude is at least that) which the picker's context floor passes.

    `base`/`headers` are mode-resolved by the caller: direct
    (https://api.anthropic.com + x-api-key) on the host, or broker
    (http://dos-broker:8788/anthropic, no key — the broker injects it) in
    the credential-free API container."""
    docs = "https://docs.anthropic.com/en/docs/about-claude/models"
    out: list[dict] = []
    after = None
    while True:
        url = f"{base}/v1/models?limit=100" + (f"&after_id={after}" if after else "")
        payload = _http_get_json(url, headers)
        for m in payload.get("data", []):
            name = m.get("id")
            if not name:
                continue
            out.append({
                "name": name,
                "display_name": m.get("display_name") or name,
                "context_window": 200_000,
                "source_url": docs,
            })
        if not payload.get("has_more"):
            break
        after = payload.get("last_id")
        if not after:
            break
    if not out:
        raise CatalogFetchError(f"{base}/v1/models returned empty model list")
    return out


# ── OpenAI ────────────────────────────────────────────────────────────────────

def _openai_display(name: str) -> str:
    """Synthesize a display label OpenAI doesn't provide.
    gpt-5.5-pro -> 'GPT-5.5 Pro'; gpt-4o-mini -> 'GPT-4o Mini'; o4-mini -> 'o4 Mini'."""
    words: list[str] = []
    for p in name.split("-"):
        if p == "gpt":
            words.append("GPT")
        elif re.fullmatch(r"o\d+", p) or re.fullmatch(r"\d[\w.]*", p):
            words.append(p)              # o3 / o4 / version tokens (5.5, 4o)
        else:
            words.append(p.capitalize())  # Pro, Mini, Nano, Codex, Max, Chat, Latest
    if len(words) >= 2 and words[0] == "GPT":
        tail = (" " + " ".join(words[2:])) if len(words) > 2 else ""
        return f"GPT-{words[1]}{tail}"
    return " ".join(words)


def _fetch_openai(base: str, headers: dict) -> list[dict]:
    """GET /v1/models, then apply the catalog policy: allowlist chat families,
    deny non-text variants, collapse dated snapshots onto their alias.

    `base`/`headers` are mode-resolved by the caller (direct + Bearer on the
    host, or broker + no key in the API container)."""
    payload = _http_get_json(base + "/v1/models", headers)
    ids = [m["id"] for m in payload.get("data", []) if m.get("id")]
    if not ids:
        raise CatalogFetchError(f"{base}/v1/models returned empty model list")

    kept = {n for n in ids if _OPENAI_ALLOW.match(n) and not _OPENAI_DENY.search(n)}
    # Snapshot dedup: drop a dated id when its bare alias also survived.
    survivors = set(kept)
    for n in kept:
        snap = _OPENAI_SNAPSHOT.match(n)
        if snap and snap.group("base") in kept:
            survivors.discard(n)

    return [{
        "name": n,
        "display_name": _openai_display(n),
        "context_window": None,  # varies per model; picker treats NULL as pass
        "source_url": f"https://platform.openai.com/docs/models/{n}",
    } for n in sorted(survivors)]


# ── Sync ──────────────────────────────────────────────────────────────────────

_PROVIDERS = {
    "anthropic": {
        "auth_ref":    "ANTHROPIC_API_KEY",
        "dialect":     "anthropic",
        "direct_base": "https://api.anthropic.com",
        "base_env":    "ANTHROPIC_BASE",   # test override for direct mode
        # Headers carried in BOTH modes (non-secret). The api-version is part
        # of the request contract, not auth, so it travels even via the broker.
        "common_headers": {"anthropic-version": _ANTHROPIC_VERSION},
        # Direct-mode auth header, added only when we hold the key ourselves.
        "auth_header": lambda key: {"x-api-key": key},
        "fetch":       _fetch_anthropic,
    },
    "openai": {
        "auth_ref":    "OPENAI_API_KEY",
        "dialect":     "openai",
        "direct_base": "https://api.openai.com",
        "base_env":    "OPENAI_BASE",
        "common_headers": {},
        "auth_header": lambda key: {"Authorization": f"Bearer {key}"},
        "fetch":       _fetch_openai,
    },
}


def _resolve_transport(provider: str) -> tuple[str, dict]:
    """Pick where the /v1/models read goes and what headers it carries.

    Broker mode (BROKER_BASE set — the credential-free API container): target
    the broker's per-provider prefix and send NO key; the broker injects it on
    egress. Direct mode (host CLI/cron): target the provider directly and add
    the key from the environment, raising MissingKeyError if it's absent.
    """
    spec    = _PROVIDERS[provider]
    headers = dict(spec["common_headers"])
    broker  = os.environ.get("BROKER_BASE")
    if broker:
        return f"{broker.rstrip('/')}/{provider}", headers
    key = os.environ.get(spec["auth_ref"])
    if not key:
        raise MissingKeyError(f"{spec['auth_ref']} not set — skipping {provider}")
    headers.update(spec["auth_header"](key))
    base = os.environ.get(spec["base_env"], spec["direct_base"]).rstrip("/")
    return base, headers


def sync_provider(con: sqlite3.Connection, provider: str) -> tuple[int, int, int]:
    """Fetch + UPSERT one provider; down-sweep its orphans.

    Returns (inserted, refreshed, deactivated). Raises MissingKeyError when in
    direct mode with no key, and CatalogFetchError on a failed listing read
    (including a broker 502 when the broker itself lacks the secret) — neither
    mutates the DB, so a skipped/failed provider leaves its rows as-is.
    """
    spec          = _PROVIDERS[provider]
    base, headers = _resolve_transport(provider)
    catalog       = spec["fetch"](base, headers)
    seen: list[str] = []
    inserted = refreshed = 0

    for m in catalog:
        name = m["name"]
        seen.append(name)
        prior = con.execute("SELECT 1 FROM models WHERE name=?", (name,)).fetchone()
        # endpoint stays NULL: the Anthropic/OpenAI SDK adapters target the
        # provider default, unlike the Ollama adapters which need a base URL.
        # context_window is set on INSERT only (omitted from the UPDATE) so a
        # hand-tuned value on an existing row is never clobbered by a refresh.
        con.execute(
            """
            INSERT INTO models
                (name, display_name, provider, endpoint, auth_ref,
                 tool_dialect, locality, status,
                 supports_tools, accepts_substrate_system,
                 context_window, source_url, last_verified)
            VALUES
                (:name, :display, :provider, NULL, :auth_ref,
                 :dialect, 'remote', 'inactive',
                 1, 1,
                 :ctx, :source_url, datetime('now'))
            ON CONFLICT(name) DO UPDATE SET
                display_name=excluded.display_name,
                provider=excluded.provider,
                auth_ref=excluded.auth_ref,
                tool_dialect=excluded.tool_dialect,
                locality='remote',
                supports_tools=1,
                accepts_substrate_system=1,
                source_url=excluded.source_url,
                last_verified=datetime('now')
            """,
            {"name": name, "display": m["display_name"], "provider": provider,
             "auth_ref": auth_ref, "dialect": spec["dialect"],
             "ctx": m["context_window"], "source_url": m["source_url"]},
        )
        if prior is None:
            inserted += 1
        else:
            refreshed += 1

    placeholders = ",".join("?" * len(seen)) or "''"
    cur = con.execute(
        f"""UPDATE models SET status='inactive'
            WHERE provider=?
              AND status='active'
              AND last_verified IS NOT NULL
              AND name NOT IN ({placeholders})""",
        [provider, *seen],
    )
    deactivated = cur.rowcount
    con.commit()
    return inserted, refreshed, deactivated


def sync(con: sqlite3.Connection, providers: list[str] | None = None) -> dict:
    """Sync the given providers (default: all). Per-provider best-effort — a
    missing key or a failed fetch is recorded under 'skipped' and the other
    providers still run. Returns {provider: {inserted, refreshed, deactivated}
    | {skipped: reason}}."""
    _load_env_file()
    result: dict = {}
    for p in (providers or list(_PROVIDERS)):
        try:
            ins, ref, deact = sync_provider(con, p)
            result[p] = {"inserted": ins, "refreshed": ref, "deactivated": deact}
        except (MissingKeyError, CatalogFetchError) as e:
            result[p] = {"skipped": str(e)}
    return result


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Sync the models registry with Anthropic/OpenAI /v1/models.")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB,
                    help=f"path to shell_db.db (default {DEFAULT_DB})")
    ap.add_argument("--provider", choices=list(_PROVIDERS),
                    help="sync only this provider (default: all)")
    args = ap.parse_args()

    if not args.db.exists():
        sys.exit(f"remote_model_sync: no DB at {args.db}")

    con = sqlite3.connect(args.db)
    try:
        res = sync(con, [args.provider] if args.provider else None)
    finally:
        con.close()

    for prov, r in res.items():
        if "skipped" in r:
            print(f"remote_model_sync ({prov}): skipped — {r['skipped']}")
        else:
            print(f"remote_model_sync ({prov}): "
                  f"{r['inserted']} inserted, {r['refreshed']} refreshed, "
                  f"{r['deactivated']} deactivated.")


if __name__ == "__main__":
    main()
