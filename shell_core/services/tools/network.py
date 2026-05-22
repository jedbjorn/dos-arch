"""network.py — network handlers (spec §07.4).

httpx — an OS-agnostic HTTP client (spec §06). url_fetch is the common-case
GET that returns a plain-text body; http_get / http_post additionally expose
the status code and let the caller set headers and a request body.

v0.2 scope: these reach any URL the dispatcher host can route to, internal
services included. A destination allow/deny list is a v0.3 concern (spec
§10.1) — single-user, single-host until then."""
from __future__ import annotations

import httpx

from .base import ToolError, ToolResult, require

_TIMEOUT  = 30        # seconds
_MAX_BODY = 100_000   # chars of response body returned to the model


def _request(method, url, **kw):
    """(True, Response) or (False, ToolError)."""
    try:
        r = httpx.request(method, url, timeout=_TIMEOUT,
                          follow_redirects=True, **kw)
    except httpx.TimeoutException:
        return False, ToolError("timeout", f"{method} {url} exceeded {_TIMEOUT}s")
    except httpx.RequestError as e:
        return False, ToolError("network_error", f"{type(e).__name__}: {e}")
    return True, r


def _truncate(text):
    if len(text) <= _MAX_BODY:
        return text
    return text[:_MAX_BODY] + "\n… (body truncated)"


def handle_http_get(params):
    if (e := require(params, "url")):
        return e
    ok, r = _request("GET", params["url"], headers=params.get("headers") or {})
    if not ok:
        return r
    return ToolResult(content=f"status: {r.status_code}\n{_truncate(r.text)}",
                      meta={"status": r.status_code, "url": params["url"]})


def handle_http_post(params):
    if (e := require(params, "url")):
        return e
    kw = {"headers": params.get("headers") or {}}
    if params.get("json") is not None:
        kw["json"] = params["json"]
    elif params.get("body") is not None:
        kw["content"] = params["body"]
    ok, r = _request("POST", params["url"], **kw)
    if not ok:
        return r
    return ToolResult(content=f"status: {r.status_code}\n{_truncate(r.text)}",
                      meta={"status": r.status_code, "url": params["url"]})


def handle_url_fetch(params):
    if (e := require(params, "url")):
        return e
    ok, r = _request("GET", params["url"])
    if not ok:
        return r
    if r.status_code >= 400:
        return ToolError("http_error", f"{r.status_code} fetching {params['url']}")
    return ToolResult(content=_truncate(r.text), meta={"status": r.status_code})
