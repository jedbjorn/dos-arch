"""API request audit logger — _log_action() writes to app_ui_logs."""
import sqlite3
from .db import DB


def _log_action(method: str, path: str, status_code: int, duration_ms: int,
                ip: str = None, user_id: int = None, shell_id: int = None):
    con = sqlite3.connect(DB)
    con.execute(
        "INSERT INTO app_ui_logs (user_id, shell_id, method, path, status_code, duration_ms, ip) VALUES (?,?,?,?,?,?,?)",
        (user_id, shell_id, method, path, status_code, duration_ms, ip)
    )
    con.commit()
    con.close()
