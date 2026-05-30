"""/keys — the secret-rotation surface backing the Keys UI (Phase 1, I3).

A thin proxy to the broker's admin API. The broker is the secrets AUTHORITY;
the substrate API never stores, encrypts, or decrypts a secret — it only relays
the operator's set/rotate/delete to the broker, which owns the encrypted store.

The broker URL + admin token come from the API's environment (BROKER_BASE set
by api-up.sh; BROKER_ADMIN_TOKEN the shared gate token). The API holds the admin
token so it can manage secrets, but never a provider key. List + metadata never
include secret values — only name, last_four, and timestamps.
"""
import json
import os
import urllib.error
import urllib.request

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from api.common.auth import _require_admin

router = APIRouter(tags=["keys"])


def _broker() -> tuple[str, str]:
    base = os.environ.get("BROKER_BASE")
    token = os.environ.get("BROKER_ADMIN_TOKEN")
    if not base or not token:
        raise HTTPException(
            status_code=503,
            detail="key management unavailable (BROKER_BASE / BROKER_ADMIN_TOKEN unset)")
    return base.rstrip("/"), token


def _call(method: str, path: str, body: dict | None = None):
    base, token = _broker()
    data = json.dumps(body).encode() if body is not None else None
    headers = {"x-admin-token": token}
    if data is not None:
        headers["content-type"] = "application/json"
    req = urllib.request.Request(f"{base}{path}", data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:200]
        # Pass through the broker's own client-error codes; collapse anything
        # else (incl. a 403 meaning our admin token is wrong) to 502 — from the
        # UI's view that's an upstream/config fault, not the user's input.
        code = e.code if e.code in (400, 404) else 502
        raise HTTPException(status_code=code, detail=f"broker: {detail}") from e
    except urllib.error.URLError as e:
        raise HTTPException(status_code=502, detail=f"broker unreachable: {e}") from e


@router.get("/keys", summary="List stored secret metadata (names + last4 + timestamps; no values)")
def list_keys(request: Request):
    _require_admin(request)
    return _call("GET", "/admin/secrets")


class _KeyBody(BaseModel):
    value: str


@router.put("/keys/{name}", summary="Set or rotate a secret")
def set_key(name: str, body: _KeyBody, request: Request):
    _require_admin(request)
    if not body.value:
        raise HTTPException(status_code=400, detail="value required")
    return _call("PUT", f"/admin/secrets/{name}", {"value": body.value})


@router.delete("/keys/{name}", summary="Delete a secret")
def delete_key(name: str, request: Request):
    _require_admin(request)
    return _call("DELETE", f"/admin/secrets/{name}")
