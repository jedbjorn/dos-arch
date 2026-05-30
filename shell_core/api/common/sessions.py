"""Server-side session helpers — the app half of the auth spine.

Sessions live in shell_db (`sessions` table); the broker IdP owns credentials.
The raw token is a CSPRNG value set as an httpOnly cookie; only its SHA-256 is
stored, so a DB leak yields hashes, not usable cookies. All expiry/renewal
arithmetic runs in SQL (`datetime('now')`) so the stored timestamp format never
has to match Python's isoformat — avoiding a silent lexicographic-compare bug.
"""
from __future__ import annotations

import hashlib
import os
import re
import secrets
import sqlite3


def cookie_secure() -> bool:
    """Cookie Secure/__Host- gating. Off in local-http dev; set AUTH_COOKIE_SECURE=1
    behind TLS (prod/CF). Single source for both the Secure attribute and the
    cookie name's __Host- prefix, so they can never disagree."""
    return os.environ.get("AUTH_COOKIE_SECURE") == "1"


# __Host-dsess in prod: the prefix forces Secure + Path=/ + no Domain, host-pinning
# the cookie (a subdomain can't set or shadow it). Plain dsess in local-http dev,
# where a __Host- cookie would be rejected outright. Resolved once at import — the
# env is fixed per process, so set and read always use the same name.
COOKIE_NAME = "__Host-dsess" if cookie_secure() else "dsess"
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


# ── UA fingerprint (audit-only bind) ──────────────────────────────────────────
# A coarse, update-tolerant fingerprint stored in sessions.ua_hash at login and
# compared on each request. It is a *signal*, not a gate: a mismatch is logged
# (a stolen cookie used from another browser surfaces here) but never logs the
# user out — minor/patch version bumps from routine auto-updates must not.
_BROWSER_RES = [
    ("Edge",    re.compile(r"Edg(?:A|iOS)?/(\d+)")),
    ("Opera",   re.compile(r"OPR/(\d+)")),
    ("Chrome",  re.compile(r"(?:CriOS|Chrome)/(\d+)")),
    ("Firefox", re.compile(r"(?:FxiOS|Firefox)/(\d+)")),
    ("Safari",  re.compile(r"Version/(\d+)[\d.]*\s+(?:Mobile/\S+\s+)?Safari/")),
]
_OS_RES = [
    ("Windows", re.compile(r"Windows NT")),
    ("iOS",     re.compile(r"iPhone|iPad|iPod")),  # before macOS (iPad UAs carry Mac OS X)
    ("macOS",   re.compile(r"Mac OS X")),
    ("Android", re.compile(r"Android")),
    ("Linux",   re.compile(r"Linux")),
]


def ua_fingerprint(ua: str | None) -> str:
    """browser-family | OS-family | browser-major-version — the stable parts.
    Minor/patch bumps don't change it; a family or major-version change does."""
    ua = ua or ""
    fam, ver = "?", "?"
    for name, rx in _BROWSER_RES:
        m = rx.search(ua)
        if m:
            fam, ver = name, m.group(1)
            break
    os_fam = next((name for name, rx in _OS_RES if rx.search(ua)), "?")
    return f"{fam}|{os_fam}|{ver}"


def note_session_ua(con: sqlite3.Connection, token: str | None,
                    ua: str | None, ip: str | None = None) -> None:
    """Record a (throttled) anomaly event if the request's coarse UA fingerprint
    differs from the one stored at session creation. Audit-only — the session is
    never invalidated. No-op if the session has no stored fingerprint or the
    fingerprints match."""
    if not token:
        return
    row = con.execute(
        "SELECT user_id, account_id, ua_hash FROM sessions WHERE token_hash = ?",
        (hash_token(token),)).fetchone()
    if not row or not row["ua_hash"]:
        return
    current = ua_fingerprint(ua)
    if current == row["ua_hash"]:
        return
    # Throttle: a persistently-mismatched cookie would otherwise log on every
    # request. At most one anomaly per user per 10 minutes.
    if con.execute(
        "SELECT 1 FROM auth_events WHERE user_id = ? AND kind = 'session_ua_mismatch' "
        "AND created_at >= datetime('now', '-10 minutes') LIMIT 1",
        (row["user_id"],)).fetchone():
        return
    con.execute(
        "INSERT INTO auth_events (user_id, account_id, kind, detail, ip) "
        "VALUES (?, ?, 'session_ua_mismatch', ?, ?)",
        (row["user_id"], row["account_id"], f"{row['ua_hash']} -> {current}", ip))
    con.commit()
