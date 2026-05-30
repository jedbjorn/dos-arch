"""/auth — user login, logout, and session identity (the app-facing auth spine).

The substrate API never holds a credential: it relays password + TOTP checks to
the broker IdP and, on success, mints a server-side session (shell_db) and sets
an httpOnly cookie. Login is stateless two-step — the client re-sends email +
password together with the TOTP code, so there is no pre-auth session to elevate
and no server-side challenge to store.

  POST /auth/login   {email, password, code?}  -> {stage: totp|enroll|authed, ...}
  POST /auth/logout
  GET  /auth/me
"""
from __future__ import annotations

import hashlib
import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from api.common import broker
from api.common.db import get_db
from api.common.sessions import (COOKIE_NAME, create_session, resolve_session,
                                 revoke_session)

router = APIRouter(tags=["auth"])


def _cookie_secure() -> bool:
    # Off in local-http dev; set AUTH_COOKIE_SECURE=1 behind TLS (prod/CF).
    return os.environ.get("AUTH_COOKIE_SECURE") == "1"


def _ua_hash(request: Request) -> str:
    return hashlib.sha256(request.headers.get("user-agent", "").encode()).hexdigest()[:32]


def _client_ip(request: Request) -> str:
    # CF-Connecting-IP is trusted only behind the proxy hop; audit only.
    return (request.headers.get("cf-connecting-ip")
            or (request.client.host if request.client else "unknown"))


def _audit(con, user_id, account_id, email, kind, request, detail=None) -> None:
    con.execute(
        "INSERT INTO auth_events (user_id, account_id, email, kind, detail, ip) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, account_id, email, kind, detail, _client_ip(request)))
    con.commit()


class LoginBody(BaseModel):
    email:    str
    password: str
    code:     str | None = None


@router.post("/auth/login", summary="Email + password (+ TOTP) login; mints a session on success")
def login(body: LoginBody, request: Request, response: Response, con=Depends(get_db)):
    email = body.email.strip()
    # 1) password — relayed to the broker IdP (uniform failure)
    _, verify = broker.post("/admin/auth/verify", {"ident": email, "password": body.password})
    if not verify.get("ok"):
        _audit(con, None, None, email, "login_fail", request, "password")
        raise HTTPException(401, "Invalid email or password.")
    account_id = verify["account_id"]
    enrolled = verify["totp_enrolled"]

    # 2) map broker identity -> app user (the handoff: relate by account_id)
    urow = con.execute(
        "SELECT user_id, is_active, is_admin FROM users WHERE account_id=?",
        (account_id,)).fetchone()
    if not urow:
        raise HTTPException(403, "No application account is linked to these credentials.")
    if not urow["is_active"]:
        _audit(con, urow["user_id"], account_id, email, "login_fail", request, "inactive")
        raise HTTPException(403, "Account is disabled.")
    user_id = urow["user_id"]

    # 3) no code yet -> tell the client which second step to render
    if not body.code:
        if enrolled:
            return {"stage": "totp"}
        _, begin = broker.post("/admin/auth/totp/enroll-begin", {"account_id": account_id})
        if "otpauth_uri" not in begin:
            raise HTTPException(500, "Could not start TOTP enrollment.")
        return {"stage": "enroll", "otpauth_uri": begin["otpauth_uri"], "secret": begin["secret"]}

    # 4) code present -> verify (enrolled) or confirm enrollment (first login)
    path = "/admin/auth/totp/verify" if enrolled else "/admin/auth/totp/enroll-confirm"
    _, res = broker.post(path, {"account_id": account_id, "code": body.code})
    if not res.get("ok"):
        _audit(con, user_id, account_id, email, "totp_fail", request)
        raise HTTPException(401, "Invalid authentication code.")
    if not enrolled:
        con.execute("UPDATE users SET totp_enrolled_at=datetime('now') WHERE user_id=?", (user_id,))
        con.commit()

    # 5) success — mint session, set cookie
    token = create_session(con, user_id, account_id, _ua_hash(request))
    _audit(con, user_id, account_id, email, "login_ok", request)
    _audit(con, user_id, account_id, email, "session_create", request)
    response.set_cookie(
        COOKIE_NAME, token, httponly=True, samesite="lax", path="/",
        max_age=2592000, secure=_cookie_secure())
    return {"stage": "authed",
            "user": {"user_id": user_id, "email": email, "is_admin": bool(urow["is_admin"])}}


@router.post("/auth/logout", summary="Revoke the current session")
def logout(request: Request, response: Response, con=Depends(get_db)):
    token = request.cookies.get(COOKIE_NAME)
    revoke_session(con, token)
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/auth/me", summary="The current session's user, or 401")
def me(request: Request, con=Depends(get_db)):
    res = resolve_session(con, request.cookies.get(COOKIE_NAME))
    if not res:
        raise HTTPException(401, "Not authenticated")
    user_id, _account_id, _is_admin = res
    row = con.execute(
        "SELECT user_id, email, username, is_admin FROM users WHERE user_id=?",
        (user_id,)).fetchone()
    return {"user_id": row["user_id"], "email": row["email"],
            "username": row["username"], "is_admin": bool(row["is_admin"])}
