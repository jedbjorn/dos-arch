#!/usr/bin/env python3
"""One-shot substrate bootstrapper.

    clone the repo  →  make bootstrap  →  good to go.

Creates a fresh substrate DB and seeds it to a working state:

  1. apply schema.sql
  2. seed every skill from assets/skills/
  3. seed Forge (the shared bootstrap shell)
  4. create the first user (interactive — username + password)
  5. seed the resident admin shell (sys-admin), owned by that user
  6. done

Refuses to run if the DB already exists — run `make db-backup` and remove
the file manually if you really want to start over.

Usage:
    python3 shell_core/scripts/bootstrap.py     (or: make bootstrap)
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from db_init import ROOT, ensure_forge, seed_skills, seed_sys_admin
from create_user import prompt_and_create

DB_PATH     = ROOT / "shell_core" / "shell_db.db"
SCHEMA_PATH = ROOT / "shell_core" / "schema.sql"


def main() -> int:
    if DB_PATH.exists():
        print(f"ERROR: {DB_PATH} already exists.", file=sys.stderr)
        print("Run 'make db-backup' then remove it manually to start over.", file=sys.stderr)
        return 1
    if not SCHEMA_PATH.exists():
        print(f"ERROR: missing {SCHEMA_PATH}", file=sys.stderr)
        return 1

    con = sqlite3.connect(DB_PATH)
    try:
        con.executescript(SCHEMA_PATH.read_text())
        print(f"  schema applied → {DB_PATH.relative_to(ROOT)}")

        seeded = seed_skills(con)
        con.commit()
        print(f"  seeded {len(seeded)} skills")

        forge_id, _ = ensure_forge(con)
        con.commit()
        print(f"  seeded Forge (shell_id={forge_id}, is_shared=1)")

        print()
        print("Create the first user — this is the substrate admin.")
        user_id = prompt_and_create(con)
        print()

        sa_id, _ = seed_sys_admin(con, user_id)
        con.commit()
        print(f"  seeded Sys-Admin (shell_id={sa_id}, owner=user_id {user_id})")
    finally:
        con.close()

    print()
    print("Bootstrap complete. Next: ./install/api-up.sh, then make up, then make launch.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
