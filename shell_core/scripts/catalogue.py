#!/usr/bin/env python3
"""Surface the substrate catalogue grouped by ref_table.

Usage:
    python3 shell_core/scripts/catalogue.py            # full listing
    python3 shell_core/scripts/catalogue.py <filter>   # substring match on name or ref_table
    python3 shell_core/scripts/catalogue.py --table dr_api          # one ref_table only
    python3 shell_core/scripts/catalogue.py --shell 1               # per-shell view
    python3 shell_core/scripts/catalogue.py --shell 1 --table dr_api

Combine: --shell N --table dr_X <filter>
"""
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

DB = Path(__file__).resolve().parents[2] / "shell_core" / "shell_db.db"


def main() -> int:
    args = sys.argv[1:]
    table_filter = None
    shell_id = None
    substring = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--table" and i + 1 < len(args):
            table_filter = args[i + 1]
            i += 2
        elif a == "--shell" and i + 1 < len(args):
            try:
                shell_id = int(args[i + 1])
            except ValueError:
                print(f"--shell expects an integer, got {args[i + 1]!r}", file=sys.stderr)
                return 1
            i += 2
        elif a in ("-h", "--help"):
            print(__doc__)
            return 0
        else:
            substring = a.lower()
            i += 1

    conn = sqlite3.connect(DB)
    if shell_id is not None:
        sql = "SELECT ref_table, name, description_short, role FROM v_shell_catalogue WHERE shell_id = ?"
        params: list = [shell_id]
        if table_filter:
            sql += " AND ref_table = ?"
            params.append(table_filter)
        sql += " ORDER BY ref_table, name"
        rows = conn.execute(sql, params).fetchall()
        rows = [(r[0], r[1], r[2], r[3]) for r in rows]
    else:
        sql = "SELECT ref_table, name, description_short FROM v_dr_catalogue"
        params = []
        if table_filter:
            sql += " WHERE ref_table = ?"
            params.append(table_filter)
        sql += " ORDER BY ref_table, name"
        rows = conn.execute(sql, params).fetchall()
        rows = [(r[0], r[1], r[2], None) for r in rows]
    conn.close()

    if substring:
        rows = [r for r in rows if substring in r[0].lower() or substring in r[1].lower()]

    if not rows:
        print("(no rows match)")
        return 0

    groups: dict = defaultdict(list)
    for ref, name, desc, role in rows:
        groups[ref].append((name, desc, role))

    name_w = max(len(name) for ref in groups for name, _, _ in groups[ref])
    name_w = min(name_w, 36)

    header = "shell catalogue" if shell_id is not None else "substrate catalogue"
    print(f"\n=== {header} ({len(rows)} rows) ===")
    for ref in sorted(groups):
        entries = groups[ref]
        print(f"\n## {ref} ({len(entries)})")
        for name, desc, role in entries:
            tail = f"  [role: {role}]" if role else ""
            disp_name = (name[: name_w - 1] + "…") if len(name) > name_w else name
            print(f"  {disp_name:<{name_w}}  {desc}{tail}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
