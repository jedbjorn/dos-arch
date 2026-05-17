#!/usr/bin/env python3
"""Apply pending schema/data migrations to the live substrate DB.

    shell_core/migrations/NNN_name.sql   →   applied in order, once each.

A migration is plain SQL — DDL, data, or both. The file carries no
transaction control; the runner wraps each migration in one. The runner:

  1. ensures the schema_migrations tracking table exists,
  2. snapshots the DB first (pre-migration backup, kept in ~/db_backups),
  3. applies each pending file in its own transaction, lowest NNN first,
  4. records it in schema_migrations,
  5. HALTS on the first failure — a half-migrated DB never goes live.

Idempotent: applied migrations are skipped. Wired into install/api-up.sh so
migrations apply at every recompose; also runnable on demand via
`make migrate` (or `--status` to preview the pending set without applying).

Usage:  python3 shell_core/scripts/migrate.py [--status]
"""
from __future__ import annotations

import re
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT       = Path(__file__).resolve().parents[2]
DB_PATH    = ROOT / "shell_core" / "shell_db.db"
MIG_DIR    = ROOT / "shell_core" / "migrations"
BACKUP_DIR = Path.home() / "db_backups" / "dos-arch"

SAFE_NAME = re.compile(r"[0-9A-Za-z._-]+\.sql")


def discovered() -> list[Path]:
    """Migration files, sorted by filename so the NNN_ prefix orders them."""
    return sorted(MIG_DIR.glob("*.sql"), key=lambda p: p.name)


def ensure_table(con: sqlite3.Connection) -> None:
    con.executescript("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            migration_id TEXT PRIMARY KEY,
            applied_at   TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)


def applied(con: sqlite3.Connection) -> set[str]:
    return {r[0] for r in con.execute("SELECT migration_id FROM schema_migrations")}


def snapshot() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = BACKUP_DIR / f"shell_db.premigrate.{ts}.db"
    shutil.copy2(DB_PATH, target)
    return target


def main() -> int:
    if not DB_PATH.exists():
        print(f"migrate: no DB at {DB_PATH} — run `make bootstrap` first.", file=sys.stderr)
        return 1

    con = sqlite3.connect(DB_PATH)
    ensure_table(con)
    done = applied(con)
    pending = [p for p in discovered() if p.name not in done]

    if "--status" in sys.argv:
        print(f"migrate: {len(done)} applied, {len(pending)} pending")
        for p in pending:
            print(f"  pending: {p.name}")
        con.close()
        return 0

    if not pending:
        print("migrate: up to date — no pending migrations.")
        con.close()
        return 0

    snap = snapshot()
    print(f"migrate: pre-migration snapshot → {snap}")
    print(f"migrate: {len(pending)} pending")

    for path in pending:
        if not SAFE_NAME.fullmatch(path.name):
            print(f"migrate: refusing unsafe migration filename: {path.name}", file=sys.stderr)
            con.close()
            return 1
        try:
            # The runner owns the transaction — the file is plain SQL. A
            # failure mid-script raises with the BEGIN still open; rollback
            # discards the partial migration whole (SQLite DDL is transactional).
            con.executescript(
                "BEGIN;\n"
                + path.read_text()
                + f"\nINSERT INTO schema_migrations (migration_id) VALUES ('{path.name}');\n"
                + "COMMIT;"
            )
        except Exception as e:
            con.rollback()
            print(f"migrate: FAILED on {path.name} — {e}", file=sys.stderr)
            print(f"migrate: halted; later migrations not applied. "
                  f"Restore from {snap} if the DB is wrong.", file=sys.stderr)
            con.close()
            return 1
        print(f"migrate: applied {path.name}")

    con.close()
    print(f"migrate: done — {len(pending)} applied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
