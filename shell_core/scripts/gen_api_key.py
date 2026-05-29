#!/usr/bin/env python3
"""Issue (or rotate) a shell's substrate-API key.

Usage:  python3 shell_core/scripts/gen_api_key.py [shortname]
        (or via Makefile: `make gen-api-key ARGS=<shortname>`)

Regenerates a high-entropy token and writes BOTH columns the auth path needs:
shells.api_key (plaintext — the dispatcher reads it per turn to set the Bearer)
and shells.api_key_hash (SHA-256 — what the auth middleware verifies). Delegates
to ensure_api_keys.rotate_key so there is one rotation primitive; the token is
printed ONCE here for convenience but is also live in the DB. Re-running rotates
the key: the new token replaces the old, and the old one stops working at once.

A random token has full entropy, so a fast hash (SHA-256) is correct here —
unlike user passwords, which need a slow KDF (scrypt). The API verifies a
presented token by SHA-256 + an indexed lookup on api_key_hash."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

SUBSTRATE_ROOT = Path(__file__).resolve().parents[2]
DB_PATH        = SUBSTRATE_ROOT / "shell_core" / "shell_db.db"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ensure_api_keys import rotate_key  # noqa: E402


def main() -> None:
    if not DB_PATH.exists():
        sys.exit(f"FATAL: DB not found at {DB_PATH}")

    shortname = (sys.argv[1] if len(sys.argv) > 1 else input("Shell shortname: ")).strip()
    if not shortname:
        sys.exit("aborted (empty shortname)")

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    row = con.execute(
        "SELECT shell_id, display_name FROM shells WHERE shortname=?", (shortname,)
    ).fetchone()
    if row is None:
        sys.exit(f"no shell with shortname '{shortname}'")

    token = rotate_key(con, row["shell_id"])
    con.commit()
    con.close()

    print(f"\nAPI key for {row['display_name']} "
          f"(shell_id={row['shell_id']}, {shortname}):\n")
    print(f"    {token}\n")
    print("Plaintext + SHA-256 are both stored; the dispatcher reads it live.")
    print("Copy it now. Re-running gen_api_key.py for this shell rotates the key.")


if __name__ == "__main__":
    main()
