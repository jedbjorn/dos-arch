#!/usr/bin/env python3
"""provision_user_1.py — give the operator (user 1) a broker auth_user.

The admin panel can create every *other* user, but it cannot create the first
admin (it would need an admin session to do so). This one-shot bootstrap closes
that gap: it creates user 1's credential record in the broker IdP and links it
to the existing app `users` row by account_id. The one-time password is printed
ONCE (login passwords are TOTP-gated; per the operator's standing call they may
be echoed here). TOTP is enrolled by user 1 on their first browser login.

Idempotent: if user 1 already has an account_id, it does nothing.

  python3 shell_core/scripts/provision_user_1.py
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "shell_core" / "shell_db.db"
ENV_FILE = Path.home() / ".config" / "dos-arch" / ".env"
BROKER_BASE = os.environ.get("BROKER_BASE", "http://127.0.0.1:8788")
EMAIL = "jedbjorn@gmail.com"


def _admin_token() -> str:
    tok = os.environ.get("BROKER_ADMIN_TOKEN")
    if tok:
        return tok
    if ENV_FILE.is_file():
        m = re.search(r"^BROKER_ADMIN_TOKEN=(.*)$", ENV_FILE.read_text(), re.M)
        if m:
            return m.group(1).strip().strip("\"'")
    sys.exit("provision: BROKER_ADMIN_TOKEN not found (env or ~/.config/dos-arch/.env)")


def _broker_post(path: str, body: dict, token: str) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"{BROKER_BASE.rstrip('/')}{path}", data=json.dumps(body).encode(),
        method="POST", headers={"x-admin-token": token, "content-type": "application/json"})
    try:
        r = urllib.request.urlopen(req, timeout=10)
        return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def main() -> int:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT user_id, email, account_id FROM users WHERE user_id=1").fetchone()
    if row is None:
        sys.exit("provision: no user_id=1 row — run bootstrap first.")
    if row["account_id"]:
        print(f"provision: user 1 already linked (account_id={row['account_id']}). Nothing to do.")
        return 0

    token = _admin_token()
    status, res = _broker_post("/admin/auth/users", {"email": EMAIL}, token)
    if status == 409:
        sys.exit(f"provision: broker already has an auth_user for {EMAIL} but user 1 "
                 "has no account_id. Reconcile manually (delete the broker row) then re-run.")
    if status != 200 or "account_id" not in res:
        sys.exit(f"provision: broker create failed (status {status}): {res}")

    con.execute("UPDATE users SET email=?, account_id=?, is_admin=1 WHERE user_id=1",
                (EMAIL, res["account_id"]))
    con.commit()
    print("provision: user 1 linked to broker auth_user.")
    print(f"  email:      {EMAIL}")
    print(f"  account_id: {res['account_id']}")
    print(f"  password:   {res['password']}   <- one-time; log in then enroll TOTP")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
