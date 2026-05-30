"""Thin client for the broker's admin API (loopback, BROKER_ADMIN_TOKEN-gated).

The broker is the credential AUTHORITY: the substrate API relays auth + secret
operations to it and never stores a credential itself. Same channel and env the
keys router uses (BROKER_BASE + BROKER_ADMIN_TOKEN). Only the substrate API holds
the admin token, so shells (which may use the egress routes) cannot reach auth.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from fastapi import HTTPException


def _cfg() -> tuple[str, str]:
    base = os.environ.get("BROKER_BASE")
    token = os.environ.get("BROKER_ADMIN_TOKEN")
    if not base or not token:
        raise HTTPException(503, "auth backend unavailable (broker not configured)")
    return base.rstrip("/"), token


def post(path: str, body: dict) -> tuple[int, dict]:
    """POST JSON to a broker admin route. Returns (status, parsed_body).
    Raises 503 if the broker is unconfigured or unreachable."""
    base, token = _cfg()
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{base}{path}", data=data, method="POST",
        headers={"x-admin-token": token, "content-type": "application/json"})
    try:
        r = urllib.request.urlopen(req, timeout=10)
        return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}
    except urllib.error.URLError:
        raise HTTPException(503, "auth backend unreachable")
