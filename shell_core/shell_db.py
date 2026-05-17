#!/usr/bin/env python3
"""
shell_db.py — shell-infra DB shell
Usage:
  python3 shell_db.py                     interactive SQL prompt
  python3 shell_db.py "SELECT ..."        run a single query
  python3 shell_db.py < query.sql         pipe a SQL file
"""
import sqlite3, sys, os

DB = os.path.join(os.path.dirname(__file__), 'shell_db.db')


def connect():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys = ON')
    con.execute('PRAGMA journal_mode = WAL')
    return con


def run(sql: str):
    con = connect()
    try:
        for stmt in sql.split(';'):
            stmt = stmt.strip()
            if not stmt:
                continue
            cur = con.execute(stmt)
            rows = cur.fetchall()
            if rows:
                keys = rows[0].keys()
                print('\t'.join(keys))
                print('\t'.join(['─' * len(k) for k in keys]))
                for r in rows:
                    print('\t'.join(str(v) if v is not None else 'NULL' for v in r))
            else:
                print(f'OK — {cur.rowcount} row(s) affected')
        con.commit()
    except Exception as e:
        print(f'Error: {e}', file=sys.stderr)
    finally:
        con.close()


def interactive():
    print(f'shell_db  |  {DB}')
    print('Type SQL, end with ; and Enter. Ctrl-D to exit.\n')
    buf = []
    try:
        while True:
            prompt = '  > ' if buf else 'sql> '
            line = input(prompt)
            buf.append(line)
            if line.rstrip().endswith(';'):
                run('\n'.join(buf))
                buf = []
    except EOFError:
        print('\nbye')


if __name__ == '__main__':
    if len(sys.argv) > 1:
        run(' '.join(sys.argv[1:]))
    elif not sys.stdin.isatty():
        run(sys.stdin.read())
    else:
        interactive()
