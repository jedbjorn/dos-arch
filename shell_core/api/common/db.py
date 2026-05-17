"""SQLite connection helper + query validators for the FastAPI app."""
import os
import sqlite3
from datetime import date
from fastapi import HTTPException

DB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'shell_db.db'))


def db():
    # check_same_thread=False because FastAPI runs sync handlers in a threadpool
    # and the Depends(get_db) cleanup may run in a different worker thread than
    # the one that opened the connection. Per-request isolation via DI means
    # connections are never shared across concurrent requests.
    con = sqlite3.connect(DB, timeout=10, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def get_db():
    con = db()
    try:
        yield con
    finally:
        con.close()


def _valid_date(value: str) -> str:
    if not value:
        return value
    try:
        date.fromisoformat(value)
        return value
    except ValueError:
        raise HTTPException(422, f"Invalid date '{value}' — expected YYYY-MM-DD")


def _enum_error(field: str, value, allowed):
    raise HTTPException(422, {
        "error": f"Invalid {field}",
        "field": field,
        "value": value,
        "accepted": list(allowed),
    })
