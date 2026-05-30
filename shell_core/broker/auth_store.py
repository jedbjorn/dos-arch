#!/usr/bin/env python3
"""auth_store.py — broker-owned user-auth store (the IdP half of the broker).

The broker is the credential AUTHORITY: user passwords and TOTP seeds live here,
in the same envelope-encrypted SQLite the secret store owns (`secrets.db`),
NEVER in the substrate app DB. The app holds only relational identity (user_id,
email, is_admin, ownership) and relates to this table by the immutable
`account_id` plus the live session token — a handoff, not a cross-DB foreign
key (decision: broker-as-IdP).

  auth_users
    account_id        uuid hex, PRIMARY KEY  — the durable cross-DB identity
    email             login identifier, UNIQUE (case-insensitive)
    password_hash     scrypt(password, salt), hex
    password_salt     CSPRNG, hex
    totp_ct           Fernet(dek).encrypt(base32 seed)  — NULL until enroll-begin
    totp_wrapped_dek  Fernet(kek).encrypt(dek)
    totp_enrolled_at  NULL until enroll-confirm — the login flow branches on this
    last_totp_step    replay guard: highest consumed TOTP step
    created_at

Crypto: scrypt for the password (stdlib hashlib; n=2**14, r=8, p=1), verified in
constant time. The TOTP seed is symmetric — verification needs the plaintext —
so it is *encrypted* (not hashed) under the same KEK-wrapped-DEK envelope the
secret store uses; a DB leak yields ciphertext only. TOTP follows RFC 6238 via
pyotp: ±1 step skew, a per-account replay guard (a consumed step can't be
reused), and an in-process attempt rate limit.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import sqlite3
import time
import uuid
from datetime import datetime, timezone

import pyotp
from cryptography.fernet import Fernet

import secrets_store  # reuse the broker's DB connection + KEK custodian

# scrypt cost parameters (CPU/memory). Bump n over time; stored hashes remain
# verifiable because params are fixed here and the salt is per-user.
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P, _DKLEN = 2**14, 8, 1, 32

# Temp-password charset: unambiguous (no 0/O/1/l/I) so a human can retype it.
_PW_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"

# In-process TOTP rate limit: max attempts per account inside the window.
_RATE_MAX, _RATE_WINDOW = 5, 60.0
_ATTEMPTS: dict[str, list[float]] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── store ─────────────────────────────────────────────────────────────────────

def init_auth(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_users (
            account_id       TEXT PRIMARY KEY,
            email            TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash    TEXT NOT NULL,
            password_salt    TEXT NOT NULL,
            totp_ct          BLOB,
            totp_wrapped_dek BLOB,
            totp_enrolled_at TEXT,
            last_totp_step   INTEGER,
            created_at       TEXT NOT NULL
        )
        """
    )
    con.commit()


def connect() -> sqlite3.Connection:
    """Open the broker DB (secrets.db) with both the secret + auth tables ready."""
    con = secrets_store.connect()  # also inits the `secrets` table
    init_auth(con)
    return con


# ── password (scrypt) ─────────────────────────────────────────────────────────

def _scrypt(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P,
        dklen=_DKLEN, maxmem=128 * 1024 * 1024)


def _hash_pw(password: str) -> tuple[str, str]:
    salt = secrets.token_bytes(16)
    return _scrypt(password, salt).hex(), salt.hex()


def _verify_pw(password: str, hash_hex: str, salt_hex: str) -> bool:
    try:
        expected = bytes.fromhex(hash_hex)
        got = _scrypt(password, bytes.fromhex(salt_hex))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got, expected)


def gen_password(n: int = 16) -> str:
    return "".join(secrets.choice(_PW_ALPHABET) for _ in range(n))


# ── TOTP seed envelope (encrypt, don't hash) ──────────────────────────────────

def _seal(value: str, kek: bytes) -> tuple[bytes, bytes]:
    dek = Fernet.generate_key()
    return Fernet(dek).encrypt(value.encode()), Fernet(kek).encrypt(dek)


def _open(ct: bytes, wrapped_dek: bytes, kek: bytes) -> str:
    dek = Fernet(kek).decrypt(wrapped_dek)
    return Fernet(dek).decrypt(ct).decode()


# ── users ─────────────────────────────────────────────────────────────────────

def create_user(con: sqlite3.Connection, email: str,
                password: str | None = None,
                account_id: str | None = None) -> dict:
    """Create an auth_user. Generates a random password if none given and an
    account_id if none given. Returns {account_id, email, password} — the
    plaintext password is returned ONCE (it is stored only as a scrypt hash)."""
    email = email.strip()
    if not email:
        raise ValueError("email required")
    account_id = account_id or uuid.uuid4().hex
    password = password or gen_password()
    h, s = _hash_pw(password)
    con.execute(
        "INSERT INTO auth_users (account_id, email, password_hash, password_salt, created_at) "
        "VALUES (?,?,?,?,?)",
        (account_id, email, h, s, _now()),
    )
    con.commit()
    return {"account_id": account_id, "email": email, "password": password}


def _row(con: sqlite3.Connection, ident: str) -> sqlite3.Row | None:
    """Look up an auth_user by account_id OR email (the two shared keys)."""
    return con.execute(
        "SELECT * FROM auth_users WHERE account_id=? OR email=? COLLATE NOCASE",
        (ident, ident),
    ).fetchone()


def verify_password(con: sqlite3.Connection, ident: str, password: str) -> dict | None:
    """Verify password for an email-or-account_id. Returns identity + TOTP state
    on success, None on any failure (uniform — never distinguishes no-user from
    bad-password)."""
    row = _row(con, ident)
    if row is None:
        # Run a dummy scrypt so timing doesn't leak account existence.
        _scrypt(password, b"\x00" * 16)
        return None
    if not _verify_pw(password, row["password_hash"], row["password_salt"]):
        return None
    return {
        "account_id": row["account_id"],
        "email": row["email"],
        "totp_enrolled": row["totp_enrolled_at"] is not None,
    }


def set_password(con: sqlite3.Connection, account_id: str, password: str) -> bool:
    h, s = _hash_pw(password)
    cur = con.execute(
        "UPDATE auth_users SET password_hash=?, password_salt=? WHERE account_id=?",
        (h, s, account_id))
    con.commit()
    return cur.rowcount > 0


def rotate_password(con: sqlite3.Connection, account_id: str) -> dict | None:
    """Mint a fresh random password for an existing account and store its hash.
    Returns {account_id, password} — the plaintext is returned ONCE — or None if
    no such account. Same contract as create_user; the broker owns password
    generation so the alphabet/length stay consistent."""
    password = gen_password()
    if not set_password(con, account_id, password):
        return None
    return {"account_id": account_id, "password": password}


# ── TOTP ──────────────────────────────────────────────────────────────────────

def _rate_ok(account_id: str) -> bool:
    now = time.monotonic()
    hist = [t for t in _ATTEMPTS.get(account_id, []) if now - t < _RATE_WINDOW]
    hist.append(now)
    _ATTEMPTS[account_id] = hist
    return len(hist) <= _RATE_MAX


def totp_enroll_begin(con: sqlite3.Connection, account_id: str, issuer: str = "dos-arch") -> dict:
    """Generate (or regenerate) a pending TOTP seed; store it sealed but leave
    `totp_enrolled_at` NULL until confirm. Returns the base32 secret + the
    otpauth:// URI for the QR. 409-worthy if already enrolled."""
    row = _row(con, account_id)
    if row is None:
        raise KeyError("no such account")
    if row["totp_enrolled_at"] is not None:
        raise ValueError("already enrolled")
    secret = pyotp.random_base32()
    ct, wrapped = _seal(secret, secrets_store.load_kek())
    con.execute(
        "UPDATE auth_users SET totp_ct=?, totp_wrapped_dek=?, last_totp_step=NULL WHERE account_id=?",
        (ct, wrapped, account_id))
    con.commit()
    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=row["email"], issuer_name=issuer)
    return {"secret": secret, "otpauth_uri": uri}


def _match_step(secret: str, code: str) -> int | None:
    """Return the TOTP step a code matches within ±1 window, else None."""
    totp = pyotp.TOTP(secret)
    now = time.time()
    code = (code or "").strip()
    for offset in (-1, 0, 1):
        t = now + offset * 30
        if hmac.compare_digest(totp.at(t), code):
            return int(t // 30)
    return None


def totp_enroll_confirm(con: sqlite3.Connection, account_id: str, code: str) -> bool:
    """Activate TOTP: verify a code against the pending sealed seed; on success
    stamp `totp_enrolled_at` and seed the replay guard."""
    if not _rate_ok(account_id):
        return False
    row = _row(con, account_id)
    if row is None or row["totp_ct"] is None or row["totp_enrolled_at"] is not None:
        return False
    secret = _open(row["totp_ct"], row["totp_wrapped_dek"], secrets_store.load_kek())
    step = _match_step(secret, code)
    if step is None:
        return False
    con.execute(
        "UPDATE auth_users SET totp_enrolled_at=?, last_totp_step=? WHERE account_id=?",
        (_now(), step, account_id))
    con.commit()
    return True


def totp_verify(con: sqlite3.Connection, account_id: str, code: str) -> bool:
    """Verify a login TOTP code for an enrolled account. Enforces the replay
    guard (a consumed step cannot be reused) and the rate limit."""
    if not _rate_ok(account_id):
        return False
    row = _row(con, account_id)
    if row is None or row["totp_enrolled_at"] is None or row["totp_ct"] is None:
        return False
    secret = _open(row["totp_ct"], row["totp_wrapped_dek"], secrets_store.load_kek())
    step = _match_step(secret, code)
    if step is None:
        return False
    if row["last_totp_step"] is not None and step <= row["last_totp_step"]:
        return False  # replay: this step (or earlier) was already consumed
    con.execute("UPDATE auth_users SET last_totp_step=? WHERE account_id=?",
                (step, account_id))
    con.commit()
    return True


def reset_totp(con: sqlite3.Connection, account_id: str) -> bool:
    """Admin recovery: clear TOTP so the user re-enrolls on next login."""
    cur = con.execute(
        "UPDATE auth_users SET totp_ct=NULL, totp_wrapped_dek=NULL, "
        "totp_enrolled_at=NULL, last_totp_step=NULL WHERE account_id=?",
        (account_id,))
    con.commit()
    return cur.rowcount > 0
