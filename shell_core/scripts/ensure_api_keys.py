#!/usr/bin/env python3
"""Ensure every shell carries a substrate-API key (generate-if-absent).

CC-102 Phase 1. A fresh bootstrap seeds forge + exprime with NO
api_key/api_key_hash — `ensure_forge`/`seed_exp_prime` don't mint, and the
old runtime mint path (run.py) was removed in the API-system cutover. The
result: token-scoped calls (caller resolved from the Bearer token, e.g.
flag.create/resolve) fail against a freshly-installed substrate.

This module is the self-healing fix: for each shell lacking either column,
mint a 32-byte urlsafe token (same shape as gen_api_key.py / shells.py),
write both `api_key` (plaintext — alpha simplification, moves to the broker
vault in CC-102 Phase 2) and `api_key_hash` (sha256, what the
auth_passthrough middleware verifies against). Idempotent: a shell with
both columns set is left untouched, so re-running is a no-op.

Wired as an API-startup hook (api/main.py) so forge/exprime get keyed on
first `make up` — the startup hook runs AFTER broker-up, unlike bootstrap.py
which runs before it. The same generate-if-absent control flow is kept in
Phase 2; only the plaintext storage backend changes (DB column → vault).

Also runnable on demand:  python3 shell_core/scripts/ensure_api_keys.py
"""
from __future__ import annotations

import hashlib
import secrets
import sqlite3
import sys
from pathlib import Path

ROOT    = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "shell_core" / "shell_db.db"


def ensure_keys(conn: sqlite3.Connection) -> list[str]:
    """Mint api_key + api_key_hash for any shell missing either column.

    Operates on the given connection; the caller owns commit/close. Returns
    the shortnames that were keyed (empty list when every shell already had
    both). A shell is considered keyed only when BOTH columns are present:
    the dispatcher needs the plaintext to carry the Bearer, the middleware
    needs the hash to verify it.
    """
    rows = conn.execute(
        "SELECT shell_id, shortname FROM shells "
        "WHERE api_key IS NULL OR api_key_hash IS NULL"
    ).fetchall()
    keyed: list[str] = []
    for shell_id, shortname in rows:
        token  = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode()).hexdigest()
        conn.execute(
            "UPDATE shells SET api_key=?, api_key_hash=? WHERE shell_id=?",
            (token, digest, shell_id),
        )
        keyed.append(shortname)
    return keyed


def main() -> int:
    if not DB_PATH.exists():
        print(f"FATAL: DB not found at {DB_PATH}", file=sys.stderr)
        return 1
    con = sqlite3.connect(DB_PATH)
    try:
        keyed = ensure_keys(con)
        con.commit()
        if keyed:
            print(f"ensure_api_keys: keyed {len(keyed)} shell(s) — "
                  f"{', '.join(keyed)}")
        else:
            print("ensure_api_keys: every shell already has a key")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
