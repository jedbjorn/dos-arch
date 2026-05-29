#!/usr/bin/env python3
"""Credential broker — egress proxy + secrets authority for the dockerized substrate.

Shell containers route outbound requests for authenticated services through
this proxy. The broker injects auth on the way out; shell containers stay
credential-free, so a prompt-injected shell has nothing to exfiltrate.

As of Phase 1 the broker is also the secrets AUTHORITY: provider keys live in
an envelope-encrypted store it owns (`secrets_store.py`), NOT in this process's
environment. Reads are live (TTL-cached), so a rotation through the admin API
takes effect without a restart.

Egress routes (path prefix -> upstream, auth injected from the store):
  /anthropic/...   -> https://api.anthropic.com     (x-api-key)
  /openai/...      -> https://api.openai.com          (Authorization: Bearer)
  /gh/...          -> https://github.com             (Authorization: Basic)
  /ghcodeload/...  -> https://codeload.github.com    (Authorization: Basic)

Admin API — secret management, gated by BROKER_ADMIN_TOKEN. This is NOT covered
by the dos-net egress trust: shells can use the egress routes but must not be
able to read/write secrets, so the admin routes require the shared token that
only the substrate API holds. Unset token => admin API fails closed (503).
  GET    /admin/secrets          -> metadata only (name, last_four, timestamps)
  PUT    /admin/secrets/{name}   -> set/rotate, body {"value": "..."}
  DELETE /admin/secrets/{name}   -> remove

Reverse proxy, NOT TLS-intercepting: no CA key, no certs in the caller.
caller -> broker is plain HTTP on dos-net; broker -> internet is real HTTPS.

  uvicorn broker:app --host 0.0.0.0 --port 8788   (image: /app, flat modules)

Env:
  BROKER_ADMIN_TOKEN                   shared token gating the admin API
  BROKER_SECRETS_DB / BROKER_KEK_PATH  passed through to secrets_store
"""
from __future__ import annotations

import base64
import hmac
import os

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import (JSONResponse, PlainTextResponse, Response,
                                  StreamingResponse)
from starlette.routing import Route

import secrets_store

# Hop-by-hop / recomputed headers — never forwarded verbatim.
_STRIP = {
    "host", "content-length", "connection", "keep-alive", "transfer-encoding",
    "upgrade", "proxy-authorization", "proxy-connection", "te", "trailer",
}


# ── auth injectors — mutate the outbound header dict, given the resolved secret
# The secret is fetched from the store by `_proxy` and passed in; injectors no
# longer reach into a startup env dict.
def _inject_anthropic(headers: dict[str, str], secret: str) -> None:
    headers.pop("authorization", None)
    headers["x-api-key"] = secret


def _inject_openai(headers: dict[str, str], secret: str) -> None:
    headers.pop("x-api-key", None)
    headers["authorization"] = "Bearer " + secret


def _inject_github(headers: dict[str, str], secret: str) -> None:
    # git-over-HTTPS Basic auth — username is ignored by GitHub for a PAT,
    # the token is validated as the password.
    headers["authorization"] = "Basic " + base64.b64encode(
        f"x-access-token:{secret}".encode()).decode()


# ── route map: prefix -> (upstream base, secret name, injector) ───────────────
ROUTES: dict[str, tuple] = {
    "anthropic":  ("https://api.anthropic.com",   "ANTHROPIC_API_KEY", _inject_anthropic),
    "openai":     ("https://api.openai.com",      "OPENAI_API_KEY",    _inject_openai),
    "gh":         ("https://github.com",          "GITHUB_TOKEN",      _inject_github),
    "ghcodeload": ("https://codeload.github.com", "GITHUB_TOKEN",      _inject_github),
}

_client = httpx.AsyncClient(
    timeout=httpx.Timeout(30.0, read=300.0), follow_redirects=False)


async def _proxy(request: Request) -> Response:
    prefix = request.path_params["prefix"]
    route = ROUTES.get(prefix)
    if route is None:
        return PlainTextResponse(f"broker: unknown route '{prefix}'\n", 404)
    upstream_base, secret_name, inject = route
    secret = secrets_store.get_cached(secret_name)
    if not secret:
        return PlainTextResponse(
            f"broker: {secret_name} not in secret store\n", 502)

    url = f"{upstream_base}/{request.path_params['rest']}"
    if request.url.query:
        url += f"?{request.url.query}"

    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in _STRIP}
    inject(headers, secret)

    try:
        upstream_req = _client.build_request(
            request.method, url, headers=headers, content=await request.body())
        resp = await _client.send(upstream_req, stream=True)
    except httpx.HTTPError as exc:
        return PlainTextResponse(f"broker: upstream error: {exc}\n", 502)

    # aiter_bytes() below decodes content-encoding; drop the now-stale header
    # so a client that never asked for compression doesn't receive raw gzip.
    out_headers = {k: v for k, v in resp.headers.items()
                   if k.lower() not in _STRIP and k.lower() != "content-encoding"}
    # Keep redirects flowing through the broker, not straight to the upstream
    # (a container that followed a raw upstream URL would have no auth).
    loc = out_headers.get("location")
    if loc:
        for pfx, (base, _, _) in ROUTES.items():
            if loc.startswith(base):
                out_headers["location"] = f"/{pfx}" + loc[len(base):]
                break

    async def _body():
        try:
            async for chunk in resp.aiter_bytes():
                yield chunk
        finally:
            await resp.aclose()

    return StreamingResponse(_body(), status_code=resp.status_code,
                             headers=out_headers)


# ── admin API (secret management) ─────────────────────────────────────────────

def _admin_guard(request: Request) -> Response | None:
    """Return an error Response if the admin call isn't authorized, else None.
    Fails closed: an unset BROKER_ADMIN_TOKEN disables the admin API entirely."""
    token = os.environ.get("BROKER_ADMIN_TOKEN", "")
    if not token:
        return JSONResponse(
            {"detail": "admin API disabled (BROKER_ADMIN_TOKEN unset)"}, 503)
    presented = request.headers.get("x-admin-token", "")
    if not hmac.compare_digest(presented, token):
        return JSONResponse({"detail": "forbidden"}, 403)
    return None


async def _admin_list(request: Request) -> Response:
    if (err := _admin_guard(request)) is not None:
        return err
    con = secrets_store.connect()
    try:
        return JSONResponse(secrets_store.list_metadata(con))
    finally:
        con.close()


async def _admin_set(request: Request) -> Response:
    if (err := _admin_guard(request)) is not None:
        return err
    name = request.path_params["name"]
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"detail": "body must be JSON {\"value\": ...}"}, 400)
    value = (body or {}).get("value")
    if not value:
        return JSONResponse({"detail": "value required"}, 400)
    con = secrets_store.connect()
    try:
        secrets_store.set_secret(con, secrets_store.load_kek(), name, value)
        meta = next(m for m in secrets_store.list_metadata(con) if m["name"] == name)
    finally:
        con.close()
    return JSONResponse(meta)


async def _admin_delete(request: Request) -> Response:
    if (err := _admin_guard(request)) is not None:
        return err
    name = request.path_params["name"]
    con = secrets_store.connect()
    try:
        cur = con.execute("DELETE FROM secrets WHERE name=?", (name,))
        con.commit()
    finally:
        con.close()
    secrets_store._CACHE.pop(name, None)
    return JSONResponse({"deleted": name, "existed": cur.rowcount > 0})


async def _health(request: Request) -> Response:
    con = secrets_store.connect()
    try:
        stored = {m["name"] for m in secrets_store.list_metadata(con)}
    finally:
        con.close()
    lines = ["broker ok"]
    for prefix, (_, secret_name, _) in ROUTES.items():
        status = "stored ✓" if secret_name in stored else "MISSING"
        lines.append(f"  /{prefix:<11} {secret_name:<18} {status}")
    lines.append(f"  admin API: "
                 f"{'enabled' if os.environ.get('BROKER_ADMIN_TOKEN') else 'DISABLED'}")
    return PlainTextResponse("\n".join(lines) + "\n")


# Admin + health routes are registered BEFORE the egress catch-all, otherwise
# `/{prefix}/{rest:path}` would swallow `/admin/secrets` (prefix='admin').
app = Starlette(routes=[
    Route("/health", _health),
    Route("/admin/secrets", _admin_list, methods=["GET"]),
    Route("/admin/secrets/{name}", _admin_set, methods=["PUT"]),
    Route("/admin/secrets/{name}", _admin_delete, methods=["DELETE"]),
    Route("/{prefix}/{rest:path}", _proxy,
          methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]),
])
