#!/usr/bin/env python3
"""
Migration 009: shells.api_key_hash — substrate-API key auth (Phase 4, slice A).

A shell authenticates to the substrate API with a Bearer token (or ?api_key=
for SSE). The API stores only the token's SHA-256; the auth_passthrough
middleware resolves it to a shell_id, and api/common/auth.py scopes that
shell to its own records.

This migration adds the storage:
  - shells.api_key_hash (TEXT) — SHA-256 hex of the shell's API key, or NULL.
  - a UNIQUE index on it for O(log n) lookup (NULLs are distinct in SQLite,
    so multiple keyless shells are fine).

It does NOT issue keys — existing shells start keyless. Issue a key per
shell with shell_core/scripts/gen_api_key.py.

Idempotent: safe to run multiple times.

Usage:
    python3 shell_core/migrations/009_shell_api_key.py <path-to-db>
"""
import sqlite3
import sys


def main(db: str) -> None:
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    actions = []

    cols = [r[1] for r in cur.execute("PRAGMA table_info(shells)")]
    if "api_key_hash" not in cols:
        cur.execute("ALTER TABLE shells ADD COLUMN api_key_hash TEXT")
        actions.append("added shells.api_key_hash")

    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_shells_api_key_hash "
        "ON shells(api_key_hash)"
    )

    conn.commit()
    conn.close()
    print(f"[009_shell_api_key] {db}: "
          f"{'; '.join(actions) if actions else 'already migrated, no-op'}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    main(sys.argv[1])
