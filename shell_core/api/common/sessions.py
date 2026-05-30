"""Server-side session helpers — the app half of the auth spine.

Sessions live in shell_db (`sessions` table); the broker IdP owns credentials.
The raw token is a CSPRNG value set as an httpOnly cookie; only its SHA-256 is
stored, so a DB leak yields hashes, not usable cookies. All expiry/renewal
arithmetic runs in SQL (`datetime('now')`) so the stored timestamp format never
has to match Python's isoformat — avoiding a silent lexicographic-compare bug.
"""
from __future__ import annotations

import hashlib
import secrets
import sqlite3

COOKIE_NAME = "dsess"          # __Host-dsess in prod (needs Secure); plain in dev http
SESSION_TTL = "+30 days"       # sliding window
_RENEW_AFTER_SECONDS = 1800    # throttle: renew expiry at most ~every 30 min


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)  # ~256 bits


def create_session(con: sqlite3.Connection, user_id: int, account_id: str | None,
                   ua_hash: str | None = None) -> str:
    """Mint a fresh session (regenerated token — never elevate a pre-auth one)
    and return the raw token to set as the cookie."""
    token = new_token()
    con.execute(
        "INSERT INTO sessions (token_hash, user_id, account_id, ua_hash, expires_at) "
        "VALUES (?, ?, ?, ?, datetime('now', ?))",
        (hash_token(token), user_id, account_id, ua_hash, SESSION_TTL),
    )
    con.commit()
    return token


def resolve_session(con: sqlite3.Connection, token: str | None):
    """Return (user_id, account_id, is_admin) for a valid session, else None.
    Applies throttled sliding renewal. All time math in SQL."""
    if not token:
        return None
    th = hash_token(token)
    row = con.execute(
        "SELECT s.user_id, s.account_id, u.is_admin "
        "FROM sessions s JOIN users u ON u.user_id = s.user_id "
        "WHERE s.token_hash = ? AND s.revoked = 0 AND s.expires_at > datetime('now')",
        (th,),
    ).fetchone()
    if not row:
        return None
    con.execute(
        "UPDATE sessions SET last_seen_at = datetime('now'), "
        "expires_at = datetime('now', ?) "
        "WHERE token_hash = ? "
        "AND (julianday('now') - julianday(last_seen_at)) * 86400 > ?",
        (SESSION_TTL, th, _RENEW_AFTER_SECONDS),
    )
    con.commit()
    return row["user_id"], row["account_id"], bool(row["is_admin"])


def revoke_session(con: sqlite3.Connection, token: str | None) -> None:
    if not token:
        return
    con.execute("UPDATE sessions SET revoked = 1 WHERE token_hash = ?", (hash_token(token),))
    con.commit()
