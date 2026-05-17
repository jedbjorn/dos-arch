#!/usr/bin/env python3
"""Create a new substrate user.

Usage:  python3 shell_core/scripts/create_user.py
        (or via Makefile: `make create-user`)

Interactive: prompts for username (must be unique), email (optional),
initials (optional), and password (twice). Stores scrypt hash + random
salt, both base64-encoded.

`create_user()` and `prompt_and_create()` are importable — the bootstrapper
reuses them to provision the first user.

Newly-created users have no shells assigned. On first launch they are
dropped straight into Forge (the shared bootstrap shell) without a
password challenge; the password set here gates subsequent logins once
they own at least one shell.
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


def create_user(con: sqlite3.Connection, username: str, password: str,
                email: str | None = None, initials: str | None = None) -> int:
    """Provision a user and return its user_id. Caller commits.

    Raises ValueError on empty username/password or a username clash.
    """
    username = username.strip()
    if not username:
        raise ValueError("empty username")
    if not password:
        raise ValueError("empty password")

    clash = con.execute(
        "SELECT user_id FROM users WHERE LOWER(username)=LOWER(?)",
        (username,),
    ).fetchone()
    if clash is not None:
        raise ValueError(f"username '{username}' already taken (user_id={clash[0]})")

    salt   = os.urandom(SALT_BYTES)
    digest = hash_password(password, salt)
    cur = con.execute(
        "INSERT INTO users (username, email, initials, password_hash, password_salt, is_active) "
        "VALUES (?, ?, ?, ?, ?, 1)",
        (
            username,
            email or None,
            initials or None,
            base64.b64encode(digest).decode("ascii"),
            base64.b64encode(salt).decode("ascii"),
        ),
    )
    return cur.lastrowid


def prompt_and_create(con: sqlite3.Connection) -> int:
    """Interactively prompt for the user fields, create the user, commit."""
    username = input("Username: ").strip()
    if not username:
        sys.exit("aborted (empty username)")
    email    = input("Email (optional): ").strip() or None
    initials = input("Initials (optional): ").strip() or None

    pw1 = getpass.getpass("Password: ")
    pw2 = getpass.getpass("Confirm: ")
    if pw1 != pw2:
        sys.exit("aborted (passwords did not match)")
    if not pw1:
        sys.exit("aborted (empty password)")

    try:
        user_id = create_user(con, username, pw1, email, initials)
    except ValueError as exc:
        sys.exit(f"aborted ({exc})")
    con.commit()
    return user_id


def main() -> None:
    if not DB_PATH.exists():
        sys.exit(f"FATAL: DB not found at {DB_PATH}")

    con = sqlite3.connect(DB_PATH)
    user_id = prompt_and_create(con)
    username = con.execute(
        "SELECT username FROM users WHERE user_id=?", (user_id,)
    ).fetchone()[0]
    con.close()
    print(f"created user '{username}' (user_id={user_id}). First login goes straight to Forge.")


if __name__ == "__main__":
    main()
