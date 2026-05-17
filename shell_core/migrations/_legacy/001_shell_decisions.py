#!/usr/bin/env python3
"""
Migration 001: shell_decisions table.

Adds shell_decisions table + index. Drops shells.decision_log TEXT column
(replaced by the table).

Idempotent: safe to run multiple times.

Usage:
    python3 shell_core/migrations/001_shell_decisions.py <path-to-db>
"""
import sqlite3
import sys
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS "shell_decisions" (
    decision_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    shell_id           INTEGER NOT NULL REFERENCES shells(shell_id),
    decision_date      DATE    NOT NULL,
    priority           TEXT    NOT NULL DEFAULT 'M' CHECK(priority IN ('M','m')),
    decision           TEXT    NOT NULL,
    rationale          TEXT,
    parent_decision_id INTEGER REFERENCES shell_decisions(decision_id),
    is_deleted         INTEGER NOT NULL DEFAULT 0,
    created_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_shell_decisions_shell_date
    ON shell_decisions(shell_id, decision_date);
"""


def column_exists(cur, table, column):
    rows = cur.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def main(db_path):
    db = Path(db_path)
    if not db.exists():
        print(f"ERROR: db not found: {db}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(db)
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON")

    actions = []

    # 1. Create shell_decisions table + index (idempotent via IF NOT EXISTS).
    table_existed = cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='shell_decisions'"
    ).fetchone() is not None
    cur.executescript(SCHEMA)
    if not table_existed:
        actions.append("created shell_decisions table + index")

    # 2. Drop shells.decision_log column if present.
    if column_exists(cur, "shells", "decision_log"):
        cur.execute("ALTER TABLE shells DROP COLUMN decision_log")
        actions.append("dropped shells.decision_log column")

    conn.commit()
    conn.close()

    if actions:
        print(f"[001_shell_decisions] {db}: {'; '.join(actions)}")
    else:
        print(f"[001_shell_decisions] {db}: already migrated, no-op")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    main(sys.argv[1])
