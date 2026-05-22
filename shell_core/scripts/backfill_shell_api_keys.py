#!/usr/bin/env python3
"""Backfill shells.api_key for any shell that has none.

Runs after migration 031 to give existing shells a key. Idempotent:
only fills rows where api_key IS NULL — re-running is a no-op once
every shell has one. Generates a 32-byte urlsafe token (same shape as
gen_api_key.py / run.py), writes both `api_key` (plaintext, alpha
simplification — see migration 031) and `api_key_hash` (sha256, what
the auth_passthrough middleware verifies against).

Wired into install/api-up.sh so a recompose lands new shells with keys
without an extra step. Also runnable standalone.
"""
from __future__ import annotations

import hashlib
import secrets
import sqlite3
import sys
from pathlib import Path

ROOT    = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "shell_core" / "shell_db.db"


def main() -> int:
    if not DB_PATH.exists():
        print(f"FATAL: DB not found at {DB_PATH}", file=sys.stderr)
        return 1
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT shell_id, shortname FROM shells WHERE api_key IS NULL"
        ).fetchall()
        if not rows:
            print("backfill_shell_api_keys: every shell already has a key")
            return 0
        for r in rows:
            token  = secrets.token_urlsafe(32)
            digest = hashlib.sha256(token.encode()).hexdigest()
            con.execute(
                "UPDATE shells SET api_key=?, api_key_hash=? WHERE shell_id=?",
                (token, digest, r["shell_id"]),
            )
        con.commit()
        print(f"backfill_shell_api_keys: filled {len(rows)} shell(s) — "
              f"{', '.join(r['shortname'] for r in rows)}")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
