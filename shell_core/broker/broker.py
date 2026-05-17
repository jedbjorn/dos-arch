#!/usr/bin/env python3
"""Credential broker — egress reverse proxy for the dockerized substrate.

Shell containers route outbound requests for authenticated services through
this proxy. The broker holds every secret and injects auth on the way out;
shell containers stay credential-free, so a prompt-injected shell has
nothing to exfiltrate.

Routes (path prefix -> upstream):
  /anthropic/...   -> https://api.anthropic.com     (injects x-api-key)
  /gh/...          -> https://github.com            (injects Authorization)
  /ghcodeload/...  -> https://codeload.github.com   (injects Authorization)

Reverse proxy, NOT TLS-intercepting: no CA key, no certs in the caller.
caller -> broker is plain HTTP; broker -> internet is real HTTPS.

The broker runs as its own container (`dos-broker`) on the shared
`dos-net` network — the trusted, secret-holding container, strictly
separate from shell containers. Shell containers reach it by Docker DNS
name (`http://dos-broker:8788`). Secrets are read from the process
environment (supplied at `docker run` via `--env-file .env`); never baked
into the image, never present in a shell container.

  uvicorn broker.broker:app --host 0.0.0.0 --port 8788   (cwd: shell_core)
"""
from __future__ import annotations

import base64
import os

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response, StreamingResponse
from starlette.routing import Route

# Hop-by-hop / recomputed headers — never forwarded verbatim.
_STRIP = {
    "host", "content-length", "connection", "keep-alive", "transfer-encoding",
    "upgrade", "proxy-authorization", "proxy-connection", "te", "trailer",
}

# Secrets — read once at startup from the process environment. The broker
# container is started with `--env-file .env`; the keys are never written
# to the image.
_SECRETS = {k: os.environ.get(k, "")
            for k in ("ANTHROPIC_API_KEY", "GITHUB_TOKEN")}


# ── auth injectors — mutate the outbound header dict in place ─────────────
def _inject_anthropic(headers: dict[str, str]) -> None:
    headers.pop("authorization", None)
    headers["x-api-key"] = _SECRETS.get("ANTHROPIC_API_KEY", "")


def _inject_github(headers: dict[str, str]) -> None:
    # git-over-HTTPS Basic auth — username is ignored by GitHub for a PAT,
    # the token is validated as the password.
    token = _SECRETS.get("GITHUB_TOKEN", "")
    headers["authorization"] = "Basic " + base64.b64encode(
        f"x-access-token:{token}".encode()).decode()


# ── route map: prefix -> (upstream base, required secret, injector) ───────
ROUTES: dict[str, tuple] = {
    "anthropic":  ("https://api.anthropic.com",   "ANTHROPIC_API_KEY", _inject_anthropic),
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
    if not _SECRETS.get(secret_name):
        return PlainTextResponse(
            f"broker: {secret_name} missing from .env\n", 502)

    url = f"{upstream_base}/{request.path_params['rest']}"
    if request.url.query:
        url += f"?{request.url.query}"

    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in _STRIP}
    inject(headers)

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


async def _health(request: Request) -> Response:
    lines = ["broker ok"]
    for prefix, (_, secret_name, _) in ROUTES.items():
        status = "auth ✓" if _SECRETS.get(secret_name) else "NO SECRET"
        lines.append(f"  /{prefix:<11} {secret_name:<18} {status}")
    return PlainTextResponse("\n".join(lines) + "\n")


app = Starlette(routes=[
    Route("/health", _health),
    Route("/{prefix}/{rest:path}", _proxy,
          methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]),
])
