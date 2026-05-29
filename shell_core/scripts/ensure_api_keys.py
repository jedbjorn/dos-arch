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
            "UPDATE shells SET api_key=?, api_key_hash=?, "
            "api_key_rotated_at=datetime('now') WHERE shell_id=?",
            (token, digest, shell_id),
        )
        keyed.append(shortname)
    return keyed


def rotate_key(conn: sqlite3.Connection, shell_id: int) -> str:
    """Replace a shell's key — regenerate plaintext + hash atomically.

    Writes api_key (plaintext, read by the dispatcher), api_key_hash (verified
    by the auth middleware), and api_key_rotated_at in ONE row UPDATE, so a
    rotation is atomic: no window where the plaintext and hash disagree. The
    old key stops working the instant the hash is replaced; the dispatcher
    re-reads api_key on its next turn and carries the new Bearer (an in-flight
    turn holding the old key will 401 once — acceptable for a manual rotate).

    Returns the new plaintext token (the CLI prints it once; the API does not
    relay it — the dispatcher reads it straight from the DB). Caller owns
    commit/close. Raises ValueError if shell_id is unknown.
    """
    row = conn.execute(
        "SELECT shell_id FROM shells WHERE shell_id=?", (shell_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"no shell with shell_id={shell_id}")
    token  = secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode()).hexdigest()
    conn.execute(
        "UPDATE shells SET api_key=?, api_key_hash=?, "
        "api_key_rotated_at=datetime('now') WHERE shell_id=?",
        (token, digest, shell_id),
    )
    return token


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
