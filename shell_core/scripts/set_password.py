#!/usr/bin/env python3
"""Set or reset a user's launcher password.

Usage:  python3 shell_core/scripts/set_password.py
        (or via Makefile: `make set-password`)

Interactive: prompts for username (matched case-insensitively against
users.username), then for a new password twice. Stores scrypt hash +
random salt, both base64-encoded, on the users row.
"""
from __future__ import annotations

import base64
import getpass
import hashlib
import os
import sqlite3
import sys
from pathlib import Path

SUBSTRATE_ROOT = Path(__file__).resolve().parents[2]
DB_PATH        = SUBSTRATE_ROOT / "shell_core" / "shell_db.db"

SCRYPT_N    = 16384
SCRYPT_R    = 8
SCRYPT_P    = 1
SCRYPT_DKLEN = 32
SALT_BYTES  = 16


def hash_password(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=SCRYPT_DKLEN,
    )


def main() -> None:
    if not DB_PATH.exists():
        sys.exit(f"FATAL: DB not found at {DB_PATH}")

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row

    username = input("Username: ").strip()
    if not username:
        sys.exit("aborted (empty username)")

    row = con.execute(
        "SELECT user_id, username FROM users WHERE LOWER(username)=LOWER(?) AND is_active=1",
        (username,),
    ).fetchone()
    if row is None:
        sys.exit(f"no active user with username '{username}'")

    pw1 = getpass.getpass("New password: ")
    pw2 = getpass.getpass("Confirm: ")
    if pw1 != pw2:
        sys.exit("aborted (passwords did not match)")
    if not pw1:
        sys.exit("aborted (empty password)")

    salt   = os.urandom(SALT_BYTES)
    digest = hash_password(pw1, salt)

    con.execute(
        "UPDATE users SET password_hash=?, password_salt=? WHERE user_id=?",
        (
            base64.b64encode(digest).decode("ascii"),
            base64.b64encode(salt).decode("ascii"),
            row["user_id"],
        ),
    )
    con.commit()
    con.close()
    print(f"password set for {row['username']} (user_id={row['user_id']})")


if __name__ == "__main__":
    main()
