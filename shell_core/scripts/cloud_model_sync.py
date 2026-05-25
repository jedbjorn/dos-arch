#!/usr/bin/env python3
"""cloud_model_sync — sync the `models` registry with Ollama Cloud's catalog.

Companion to `model_sync.py` (which tracks the *local* Ollama daemon's
installed set). Ollama Cloud exposes a public `/api/tags` that lists every
model the hosted service can run; this script reads that list and UPSERTs
one `provider='ollama_cloud'` row per model. Discovery is anonymous — the
API key (OLLAMA_CLOUD_API_KEY) is only needed at chat time, not for
catalog reads.

New rows land as `status='inactive'`: the activation UI (PR 3) is the
opt-in surface. On conflict the upsert preserves the existing `status` —
a row a user activated stays active even if the upsert re-runs.

`last_verified` is set on every successful upsert. The down-sweep at the
end uses that as the discriminator: a cloud row whose `last_verified` is
NOT NULL but whose name is absent from the latest `/api/tags` gets
flipped to inactive — same idea as `model_sync` flipping uninstalled
local rows. Hand-inserted rows that were never synced
(`last_verified IS NULL`, e.g. the PR 1 smoke row) are left alone, so
they survive without manual exemption logic.

Usage:
    python3 shell_core/scripts/cloud_model_sync.py [--db PATH]

Env:
    OLLAMA_CLOUD_BASE   override the cloud base (default https://ollama.com)
"""
import argparse
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT       = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "shell_core" / "shell_db.db"

_DEFAULT_BASE = "https://ollama.com"
_AUTH_REF     = "OLLAMA_CLOUD_API_KEY"
_TIMEOUT      = 30


class CatalogFetchError(RuntimeError):
    """The /api/tags read failed — network error, HTTP error, or empty payload.

    Raised by `_fetch_catalog` so callers can decide how to surface it: the
    CLI `main` prints and exits non-zero; the API endpoint catches it and
    returns a 502 with the message intact.
    """


def _cloud_base() -> str:
    return os.environ.get("OLLAMA_CLOUD_BASE", _DEFAULT_BASE).rstrip("/")


def _fetch_catalog(base: str) -> list[dict]:
    """GET /api/tags from Ollama Cloud. No auth required for discovery."""
    url = base + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise CatalogFetchError(
            f"HTTP {e.code} from {url}: "
            f"{e.read().decode(errors='replace')[:200]}") from e
    except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
        raise CatalogFetchError(f"unreachable {url}: {e}") from e
    models = payload.get("models") or []
    if not models:
        raise CatalogFetchError(f"{url} returned empty model list")
    return models


def sync(con: sqlite3.Connection, base: str) -> tuple[int, int, int]:
    """Upsert one row per /api/tags entry; down-sweep orphans.

    Returns (inserted, refreshed, deactivated). `refreshed` covers any
    row that already existed (status preserved) — the upsert touches
    last_verified + display_name + endpoint + version on every run.
    """
    catalog = _fetch_catalog(base)
    seen: list[str] = []
    inserted = refreshed = 0

    for m in catalog:
        name = m.get("name")
        if not name:
            continue
        seen.append(name)
        prior = con.execute(
            "SELECT 1 FROM models WHERE name=?", (name,),
        ).fetchone()
        digest = (m.get("digest") or "")[:12] or None
        # display_name carries a "(cloud)" suffix so the picker's group
        # header reads cleanly — the frontend modelLabel strips it (same
        # convention as `model_sync` for local rows).
        con.execute(
            """
            INSERT INTO models
                (name, display_name, provider, endpoint, auth_ref,
                 tool_dialect, locality, status,
                 supports_tools, accepts_substrate_system,
                 version, last_verified)
            VALUES
                (:name, :display, 'ollama_cloud', :endpoint, :auth_ref,
                 'openai', 'remote', 'inactive',
                 1, 1,
                 :version, datetime('now'))
            ON CONFLICT(name) DO UPDATE SET
                provider='ollama_cloud',
                endpoint=excluded.endpoint,
                auth_ref=excluded.auth_ref,
                tool_dialect='openai',
                locality='remote',
                supports_tools=1,
                accepts_substrate_system=1,
                version=excluded.version,
                last_verified=datetime('now')
            """,
            {"name": name, "display": f"{name} (cloud)",
             "endpoint": base, "auth_ref": _AUTH_REF,
             "version": digest},
        )
        if prior is None:
            inserted += 1
        else:
            refreshed += 1

    # Down-sweep — only previously-synced rows (last_verified IS NOT NULL)
    # are eligible. Hand-inserted rows (e.g. the PR 1 smoke row) carry NULL
    # last_verified and are exempt; nothing the user pinned by hand gets
    # silently disabled by a catalog refresh.
    placeholders = ",".join("?" * len(seen)) or "''"
    cur = con.execute(
        f"""UPDATE models SET status='inactive'
            WHERE provider='ollama_cloud'
              AND status='active'
              AND last_verified IS NOT NULL
              AND name NOT IN ({placeholders})""",
        seen,
    )
    deactivated = cur.rowcount
    con.commit()
    return inserted, refreshed, deactivated


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Sync the models registry with Ollama Cloud's /api/tags.")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB,
                    help=f"path to shell_db.db (default {DEFAULT_DB})")
    args = ap.parse_args()

    if not args.db.exists():
        sys.exit(f"cloud_model_sync: no DB at {args.db}")

    base = _cloud_base()
    con = sqlite3.connect(args.db)
    try:
        try:
            inserted, refreshed, deactivated = sync(con, base)
        except CatalogFetchError as e:
            sys.exit(f"cloud_model_sync: {e}")
    finally:
        con.close()
    print(f"cloud_model_sync ({base}): "
          f"{inserted} inserted, {refreshed} refreshed, "
          f"{deactivated} deactivated.")


if __name__ == "__main__":
    main()
