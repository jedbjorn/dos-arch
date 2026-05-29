#!/usr/bin/env python3
"""secrets_store.py — the broker-owned encrypted secret store (Phase 1).

Envelope encryption. Each secret is sealed under its own data key (DEK); the
DEK is wrapped by a key-encryption key (KEK). Ciphertext + wrapped DEK live in
`secrets.db`; the KEK never touches the database. A DB or backup leak therefore
yields only ciphertext — the KEK is the single thing to protect and keep out of
git.

The KEK comes from a pluggable custodian. Today that is a 0600 file on disk
(`load_kek`); a cloud KMS later is a swap of that one function, not a change to
the data layer — which is the whole point of the envelope split (decision #136).

Both layers use Fernet (cryptography lib: AES-128-CBC + HMAC-SHA256,
authenticated and timestamped) — no hand-rolled crypto. KEK rotation re-wraps
the small per-secret DEKs and never has to touch the (larger) ciphertext.

The read path is hot — the broker injects a secret on every proxied egress
request — so `get_cached` keeps decrypted values in-process for `CACHE_TTL`
seconds. A rotation lands within the TTL with no restart, and we avoid a
SQLite open + decrypt per request.

CLI (run inside the broker image; `cwd` = shell_core):
    python -m broker.secrets_store init
    python -m broker.secrets_store set NAME [--value V]      # value via stdin if omitted
    python -m broker.secrets_store import-env NAME [NAME...]  # seed from os.environ (one-time migration)
    python -m broker.secrets_store list                       # metadata only — never plaintext
    python -m broker.secrets_store rotate-kek --new PATH      # re-wrap every DEK under a new KEK file

Env:
    BROKER_SECRETS_DB   path to secrets.db   (default /secrets/secrets.db)
    BROKER_KEK_PATH     path to the KEK file (default /secrets/master.key)
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet

DEFAULT_DB  = "/secrets/secrets.db"
DEFAULT_KEK = "/secrets/master.key"
CACHE_TTL   = 10  # seconds a decrypted value is reused on the hot path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── KEK custodian (file impl; swap this one function for KMS later) ───────────

def kek_path() -> Path:
    return Path(os.environ.get("BROKER_KEK_PATH", DEFAULT_KEK))


def load_kek(path: Path | None = None) -> bytes:
    """Return the KEK (a Fernet key). Generates one at `path` (0600) if absent —
    so a fresh broker is self-bootstrapping; the install script formalizes this
    by pre-creating the file. The parent dir must already exist (the broker
    mounts it). Raises if the file exists but isn't a valid Fernet key."""
    p = path or kek_path()
    if p.exists():
        key = p.read_bytes().strip()
        Fernet(key)  # validate — raises ValueError on a malformed key
        return key
    key = Fernet.generate_key()
    p.write_bytes(key)
    p.chmod(0o600)
    return key


# ── store ─────────────────────────────────────────────────────────────────────

def db_path() -> str:
    return os.environ.get("BROKER_SECRETS_DB", DEFAULT_DB)


def connect(path: str | None = None) -> sqlite3.Connection:
    con = sqlite3.connect(path or db_path())
    con.row_factory = sqlite3.Row
    init_store(con)
    return con


def init_store(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS secrets (
            name            TEXT PRIMARY KEY,
            ciphertext      BLOB NOT NULL,   -- Fernet(dek).encrypt(secret)
            wrapped_dek     BLOB NOT NULL,   -- Fernet(kek).encrypt(dek)
            last_four       TEXT,            -- for UI display; never the whole secret
            created_at      TEXT NOT NULL,
            last_rotated_at TEXT NOT NULL
        )
        """
    )
    con.commit()


def set_secret(con: sqlite3.Connection, kek: bytes, name: str, value: str) -> None:
    """Seal `value` under a fresh DEK, wrap the DEK under the KEK, upsert.
    A re-set (rotation of the secret value) generates a NEW DEK and ciphertext;
    `created_at` is preserved, `last_rotated_at` advances."""
    dek         = Fernet.generate_key()
    ciphertext  = Fernet(dek).encrypt(value.encode())
    wrapped_dek = Fernet(kek).encrypt(dek)
    con.execute(
        """
        INSERT INTO secrets (name, ciphertext, wrapped_dek, last_four,
                             created_at, last_rotated_at)
        VALUES (:name, :ct, :wd, :l4, :now, :now)
        ON CONFLICT(name) DO UPDATE SET
            ciphertext      = excluded.ciphertext,
            wrapped_dek     = excluded.wrapped_dek,
            last_four       = excluded.last_four,
            last_rotated_at = excluded.last_rotated_at
        """,
        {"name": name, "ct": ciphertext, "wd": wrapped_dek,
         "l4": value[-4:], "now": _now()},
    )
    con.commit()
    _CACHE.pop(name, None)  # next read re-fetches the rotated value


def get_secret(con: sqlite3.Connection, kek: bytes, name: str) -> str | None:
    """Unwrap the DEK with the KEK, decrypt the ciphertext. None if absent."""
    row = con.execute(
        "SELECT ciphertext, wrapped_dek FROM secrets WHERE name=?", (name,)
    ).fetchone()
    if row is None:
        return None
    dek = Fernet(kek).decrypt(row["wrapped_dek"])
    return Fernet(dek).decrypt(row["ciphertext"]).decode()


def list_metadata(con: sqlite3.Connection) -> list[dict]:
    """Name + last_four + timestamps for the Keys UI. Never returns plaintext."""
    rows = con.execute(
        "SELECT name, last_four, created_at, last_rotated_at "
        "FROM secrets ORDER BY name"
    ).fetchall()
    return [dict(r) for r in rows]


def import_env(con: sqlite3.Connection, kek: bytes, names: list[str]) -> list[str]:
    """One-time migration: seed each name from os.environ if present AND not
    already stored. Idempotent — re-running never clobbers a stored value with
    a (possibly stale) env one. Returns the names actually imported."""
    imported: list[str] = []
    for name in names:
        val = os.environ.get(name)
        if not val:
            continue
        if con.execute("SELECT 1 FROM secrets WHERE name=?", (name,)).fetchone():
            continue
        set_secret(con, kek, name, val)
        imported.append(name)
    return imported


def rotate_kek(con: sqlite3.Connection, old_kek: bytes, new_kek: bytes) -> int:
    """Re-wrap every DEK from old_kek to new_kek. Ciphertext is untouched — only
    the small wrapped_dek changes. Returns the row count re-wrapped. Caller is
    responsible for swapping the KEK file after this returns."""
    rows = con.execute("SELECT name, wrapped_dek FROM secrets").fetchall()
    for r in rows:
        dek = Fernet(old_kek).decrypt(r["wrapped_dek"])
        con.execute("UPDATE secrets SET wrapped_dek=? WHERE name=?",
                    (Fernet(new_kek).encrypt(dek), r["name"]))
    con.commit()
    _CACHE.clear()
    return len(rows)


# ── hot-path cache ─────────────────────────────────────────────────────────────

_CACHE: dict[str, tuple[str, float]] = {}


def get_cached(name: str, ttl: int = CACHE_TTL) -> str | None:
    """Hot-path accessor for the broker. Returns the decrypted secret, reusing a
    value cached within `ttl` seconds. Opens its own short-lived connection so it
    is safe to call from request handlers. None if the secret isn't stored."""
    hit = _CACHE.get(name)
    if hit and hit[1] > time.monotonic():
        return hit[0]
    con = connect()
    try:
        val = get_secret(con, load_kek(), name)
    finally:
        con.close()
    if val is not None:
        _CACHE[name] = (val, time.monotonic() + ttl)
    return val


# ── CLI ─────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Broker encrypted secret store.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="create the store + KEK if absent")
    sp = sub.add_parser("set", help="store/rotate a secret value")
    sp.add_argument("name")
    sp.add_argument("--value", help="value (omit to read from stdin)")
    ip = sub.add_parser("import-env", help="seed names from os.environ (one-time)")
    ip.add_argument("names", nargs="+")
    sub.add_parser("list", help="list metadata (no plaintext)")
    rp = sub.add_parser("rotate-kek", help="re-wrap all DEKs under a new KEK")
    rp.add_argument("--new", required=True, help="path to the new KEK file")
    args = ap.parse_args(argv)

    con = connect()
    try:
        if args.cmd == "init":
            load_kek()
            print(f"store ready at {db_path()}; KEK at {kek_path()}")
        elif args.cmd == "set":
            val = args.value if args.value is not None else sys.stdin.readline().rstrip("\n")
            if not val:
                return _err("empty value")
            set_secret(con, load_kek(), args.name, val)
            print(f"set {args.name} (…{val[-4:]})")
        elif args.cmd == "import-env":
            done = import_env(con, load_kek(), args.names)
            print(f"imported: {', '.join(done) if done else '(none — already stored or unset)'}")
        elif args.cmd == "list":
            for m in list_metadata(con):
                print(f"  {m['name']:20} …{m['last_four']}  rotated {m['last_rotated_at']}")
        elif args.cmd == "rotate-kek":
            new = Path(args.new)
            if not new.exists():
                return _err(f"new KEK file {new} not found (generate it first)")
            n = rotate_kek(con, load_kek(), load_kek(new))
            print(f"re-wrapped {n} secret(s); now point BROKER_KEK_PATH at {new}")
    finally:
        con.close()
    return 0


def _err(msg: str) -> int:
    print(f"secrets_store: {msg}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
