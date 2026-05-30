from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.routing import Match
import hashlib
import hmac
import os
import time
from urllib.parse import urlsplit

# Shared secret proving a request came through the SvelteKit trust seam (the
# /api proxy). The browser never holds it; only the UI server process does. When
# set, a request that carries it is a "proxied" (user-surface) request — and an
# unauthenticated proxied request resolves to NO user, not the legacy user 1.
_INTERNAL_SECRET = os.environ.get("INTERNAL_PROXY_SECRET", "")

# CSRF backstop: a proxied (browser) mutation must carry an Origin/Referer in
# this allowlist. SameSite=Lax already strips the session cookie from cross-site
# mutations; this is the stateless defense-in-depth layer behind it. Only
# proxied (browser-surface) requests are checked — api-key shells, the
# dispatcher, and CLI callers send no Origin and are never subject to it.
# Comma-separated; the operator sets the public origin in .env (loadEnv →
# dosarch-api). Dev origins default.
_ALLOWED_ORIGINS = {
    o.strip().rstrip("/")
    for o in os.environ.get(
        "APP_ALLOWED_ORIGINS", "http://localhost:5174,http://localhost:5173"
    ).split(",")
    if o.strip()
}

from api.common.db import db
from api.common.logging import _log_action
from api.common.errors import _log_5xx
from api.common.sessions import COOKIE_NAME, note_session_ua, resolve_session

app = FastAPI(title="dos-arch API")


# ── BR-052: unhandled exception sink ──────────────────────────────────────────
# Any exception that escapes a route handler returns a generic 500 with a
# correlation id. The full traceback is logged server-side; the client never
# sees exception text, file paths, SQL fragments, or stack frames.
@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    rid = _log_5xx(f"unhandled {request.method} {request.url.path}", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error (request_id={rid})"},
    )


# ── Middleware ────────────────────────────────────────────────────────────────
# The HTTP surface stays single-user (every request is user_id=1 + is_admin).
# On top of that a shell may authenticate with its substrate-API key — a
# Bearer token, or ?api_key= for SSE. A valid key resolves request.state
# .shell_id; the helpers in api/common/auth.py then scope that shell to its
# own records. No key = no shell context = the localhost UI, full access
# (unchanged). A key that matches no shell is rejected with 401.

MUTATION_METHODS = {"POST", "PATCH", "PUT", "DELETE"}


def _resolve_caller_shell(request: Request) -> tuple[int | None, str | None, bool, bool]:
    """Resolve an API-key token to a shell. Returns
    (shell_id, shortname, is_admin, bad); `bad` is True when a token was
    presented but matched no shell. No token at all → (None, None, False, False)."""
    token = ""
    authz = request.headers.get("authorization", "")
    if authz[:7].lower() == "bearer ":
        token = authz[7:].strip()
    if not token:
        token = (request.query_params.get("api_key") or "").strip()
    if not token:
        return None, None, False, False
    digest = hashlib.sha256(token.encode()).hexdigest()
    con = db()
    try:
        row = con.execute(
            "SELECT shell_id, shortname, is_admin FROM shells WHERE api_key_hash=?", (digest,)
        ).fetchone()
    finally:
        con.close()
    if row is None:
        return None, None, False, True
    return row["shell_id"], row["shortname"], bool(row["is_admin"]), False


def _resolve_session(request: Request):
    """Resolve the session cookie to (user_id, account_id, is_admin), or None."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    con = db()
    try:
        res = resolve_session(con, token)
        if res is not None:
            # Audit-only UA-binding signal — logs a mismatch, never logs out.
            note_session_ua(
                con, token, request.headers.get("user-agent", ""),
                request.headers.get("cf-connecting-ip")
                or (request.client.host if request.client else None))
        return res
    finally:
        con.close()


def _is_proxied(request: Request) -> bool:
    """True iff the request carries a valid internal-proxy secret — i.e. it came
    through the SvelteKit trust seam (a user-surface request). Raises on a
    present-but-wrong secret (caller is forging the proxy hop)."""
    if not _INTERNAL_SECRET:
        return False
    presented = request.headers.get("x-internal-auth", "")
    if not presented:
        return False
    if not hmac.compare_digest(presented, _INTERNAL_SECRET):
        raise PermissionError("bad internal-proxy secret")
    return True


def _origin_allowed(request: Request) -> bool:
    """True if a browser mutation's Origin (or, as a fallback, its Referer host)
    is in the allowlist. False when neither header is present — a browser always
    sends one on a state-changing request, so absence is treated as cross-origin."""
    origin = request.headers.get("origin", "").strip()
    if not origin:
        ref = request.headers.get("referer", "").strip()
        if ref:
            p = urlsplit(ref)
            if p.scheme and p.netloc:
                origin = f"{p.scheme}://{p.netloc}"
    if not origin:
        return False
    return origin.rstrip("/") in _ALLOWED_ORIGINS


@app.middleware("http")
async def auth_passthrough(request: Request, call_next):
    shell_id, shell_name, shell_is_admin, bad = _resolve_caller_shell(request)
    if bad:
        return JSONResponse(status_code=401, content={"detail": "Invalid API key."})
    try:
        proxied = _is_proxied(request)
    except PermissionError:
        return JSONResponse(status_code=401, content={"detail": "Bad proxy credential."})
    # CSRF backstop on the browser surface: a proxied state-changing request must
    # carry an allow-listed Origin. SameSite=Lax is the primary defense; this
    # rejects the residual cases (a side-effecting GET added later, a forced
    # SameSite relaxation) before any handler runs.
    if proxied and request.method in MUTATION_METHODS and not _origin_allowed(request):
        return JSONResponse(status_code=403, content={"detail": "Cross-origin request rejected."})
    sess = _resolve_session(request)
    if sess is not None:
        # The multi-tenant path: a valid session cookie sets the real user.
        request.state.user_id, request.state.account_id, request.state.is_admin = sess
    elif shell_id is not None:
        # Authenticated api-key (shell) caller. Authorization is by shell scope
        # (shell_id / shell_is_admin, enforced in api/common/auth.py); the acting
        # user is the single substrate owner. NOT admin at the user level — a
        # shell's admin rights are shell_is_admin, never an implicit user-admin.
        request.state.user_id    = 1
        request.state.account_id = None
        request.state.is_admin   = False
    else:
        # No session and no api key: unauthenticated. Browser requests (proxied)
        # are redirected to /login by hooks.server.js; anonymous direct callers
        # (the dispatcher's tokenless reads, local curl) get NO user and NO admin.
        # This closes the fail-open where any non-proxied request — including the
        # case where INTERNAL_PROXY_SECRET is unset — silently became user 1 +
        # admin. Admin now requires a real session; it is never the default.
        request.state.user_id    = None
        request.state.account_id = None
        request.state.is_admin   = False
    request.state.shell_id       = shell_id
    request.state.shell_name     = shell_name
    request.state.shell_is_admin = shell_is_admin
    t0 = time.monotonic()
    response = await call_next(request)
    if request.method in MUTATION_METHODS:
        duration = int((time.monotonic() - t0) * 1000)
        ip = request.client.host if request.client else "unknown"
        _log_action(request.method, request.url.path, response.status_code, duration, ip,
                    user_id=getattr(request.state, "user_id", None) or 1)
    return response

# Always-allowed query params (used outside individual endpoint signatures).
# api_key: fallback auth for SSE (EventSource can't send custom headers — see L&S 18).
_ALWAYS_ALLOWED_QS = {"api_key"}

@app.middleware("http")
async def strict_query_params(request: Request, call_next):
    """Reject unknown query params with 422 so silent-drop bugs are impossible.
    Matches the incoming request against the router and compares query-param
    keys against the matched route's declared params."""
    if not request.query_params:
        return await call_next(request)
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        match, _ = route.matches(request.scope)
        if match != Match.FULL:
            continue
        if request.method not in route.methods:
            continue
        allowed = {p.name for p in route.dependant.query_params} | _ALWAYS_ALLOWED_QS
        unknown = set(request.query_params.keys()) - allowed
        if unknown:
            return JSONResponse(
                status_code=422,
                content={
                    "detail": f"Unknown query parameter(s): {sorted(unknown)}. "
                              f"Allowed on {request.method} {route.path}: {sorted(allowed - _ALWAYS_ALLOWED_QS) or '(none)'}."
                },
            )
        break
    return await call_next(request)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routers ───────────────────────────────────────────────────────────────────

from api.routers.shells import router as shells_router
app.include_router(shells_router)

from api.routers.users import router as users_router
app.include_router(users_router)

from api.routers.skills import router as skills_router
app.include_router(skills_router)

from api.routers.tools import router as tools_router
app.include_router(tools_router)

from api.routers.models import router as models_router
app.include_router(models_router)

from api.routers.keys import router as keys_router
app.include_router(keys_router)

from api.routers.flags import router as flags_router
app.include_router(flags_router)

from api.routers.contacts import router as contacts_router
app.include_router(contacts_router)

from api.routers.emails import router as emails_router
app.include_router(emails_router)

from api.routers.events import router as events_router
app.include_router(events_router)

from api.routers.catalogue import router as catalogue_router
app.include_router(catalogue_router)

from api.routers.admin import router as admin_router
app.include_router(admin_router)

from api.routers.auth import router as auth_router
app.include_router(auth_router)


@app.get("/health")
def health():
    return {"status": "ok"}


# ── Catalogue sync on startup ─────────────────────────────────────────────────
# Every API restart refreshes dr_router + dr_api from the live route set.
# Idempotent (UPSERT keyed on natural unique keys), best-effort (failures don't
# block startup). The CLI variant `python3 shell_core/scripts/dr_sync.py` runs
# the same logic on demand.

@app.on_event("startup")
async def _populate_catalogue() -> None:
    import sqlite3
    import sys as _sys
    from pathlib import Path
    here = Path(__file__).resolve()
    scripts_dir = here.parents[1] / "scripts"
    db_path     = here.parents[2] / "shell_core" / "shell_db.db"
    _sys.path.insert(0, str(scripts_dir))
    try:
        from dr_sync import sync_all, _record_run  # type: ignore[import-not-found]
        conn = sqlite3.connect(db_path)
        try:
            results = sync_all(conn, app=app)
            _record_run(conn, "startup", results)
            conn.commit()
            for target, counts in results.items():
                if "error" in counts:
                    print(f"[catalogue] startup sync — {target}: ERROR {counts['error']}", flush=True)
                else:
                    parts = ", ".join(
                        f"{surface}: {c['insert']} ins / {c['update']} upd"
                        for surface, c in counts.items()
                    )
                    print(f"[catalogue] startup sync — {target}: {parts}", flush=True)
        finally:
            conn.close()
    except Exception as e:
        print(f"[catalogue] startup sync FAILED: {e!r}", flush=True)
    finally:
        if str(scripts_dir) in _sys.path:
            _sys.path.remove(str(scripts_dir))


# ── Ensure shell API keys on startup (CC-102 Phase 1) ─────────────────────────
# A fresh bootstrap seeds forge + sysadmin with no api_key/api_key_hash, so
# token-scoped calls (caller resolved from the Bearer, e.g. flag.create) fail.
# This hook mints a key for any keyless shell on every `make up`. Idempotent
# (shells with both columns are skipped), self-healing, and best-effort — a
# failure here must not block startup. MUST be a startup hook (runs after
# broker-up) not bootstrap.py (runs before it). The same generate-if-absent
# flow is kept in Phase 2; only the plaintext backend moves (DB → broker vault).

@app.on_event("startup")
async def _ensure_shell_keys() -> None:
    import sqlite3
    import sys as _sys
    from pathlib import Path
    here        = Path(__file__).resolve()
    scripts_dir = here.parents[1] / "scripts"
    db_path     = here.parents[2] / "shell_core" / "shell_db.db"
    _sys.path.insert(0, str(scripts_dir))
    try:
        from ensure_api_keys import ensure_keys  # type: ignore[import-not-found]
        conn = sqlite3.connect(db_path)
        try:
            keyed = ensure_keys(conn)
            conn.commit()
            if keyed:
                print(f"[shell-keys] startup: keyed {len(keyed)} shell(s) — "
                      f"{', '.join(keyed)}", flush=True)
            else:
                print("[shell-keys] startup: every shell already keyed", flush=True)
        finally:
            conn.close()
    except Exception as e:
        print(f"[shell-keys] startup FAILED: {e!r}", flush=True)
    finally:
        if str(scripts_dir) in _sys.path:
            _sys.path.remove(str(scripts_dir))


# ── Cloud model catalog sync on startup ──────────────────────────────────────
# Refresh the `models` rows for provider='ollama_cloud' from Ollama Cloud's
# anonymous /api/tags on every API restart. Best-effort: a network failure
# (Ollama Cloud unreachable) must not block startup. The daily refresh comes
# from cron (install/cron-install.sh); this hook just ensures a freshly-booted
# substrate doesn't serve a stale catalog until 04:15.

@app.on_event("startup")
async def _sync_cloud_models() -> None:
    import sqlite3
    import sys as _sys
    from pathlib import Path
    here        = Path(__file__).resolve()
    scripts_dir = here.parents[1] / "scripts"
    db_path     = here.parents[2] / "shell_core" / "shell_db.db"
    _sys.path.insert(0, str(scripts_dir))
    try:
        from cloud_model_sync import sync as _sync, _cloud_base, CatalogFetchError  # type: ignore[import-not-found]
        conn = sqlite3.connect(db_path)
        try:
            try:
                inserted, refreshed, deactivated = _sync(conn, _cloud_base())
                print(
                    f"[cloud-models] startup sync: "
                    f"{inserted} inserted, {refreshed} refreshed, "
                    f"{deactivated} deactivated.",
                    flush=True,
                )
            except CatalogFetchError as e:
                print(f"[cloud-models] startup sync skipped: {e}", flush=True)
        finally:
            conn.close()
    except Exception as e:
        print(f"[cloud-models] startup sync FAILED: {e!r}", flush=True)
    finally:
        if str(scripts_dir) in _sys.path:
            _sys.path.remove(str(scripts_dir))


# ── First-party remote model catalog sync on startup ─────────────────────────
# Refresh the Anthropic + OpenAI `models` rows from each provider's /v1/models
# on every API restart, so a freshly-booted substrate discovers a new Opus/GPT
# release without waiting for the nightly cron. Best-effort and per-provider:
# a missing key (the API container may not carry one) or an unreachable
# provider is logged and skipped — never blocks startup. The keys reach this
# process via the dos-api container's --env-file (install/api-up.sh).

@app.on_event("startup")
async def _sync_remote_models() -> None:
    import sqlite3
    import sys as _sys
    from pathlib import Path
    here        = Path(__file__).resolve()
    scripts_dir = here.parents[1] / "scripts"
    db_path     = here.parents[2] / "shell_core" / "shell_db.db"
    _sys.path.insert(0, str(scripts_dir))
    try:
        from remote_model_sync import sync as _sync  # type: ignore[import-not-found]
        conn = sqlite3.connect(db_path)
        try:
            for prov, r in _sync(conn).items():
                if "skipped" in r:
                    print(f"[remote-models] startup sync ({prov}) skipped: "
                          f"{r['skipped']}", flush=True)
                else:
                    print(f"[remote-models] startup sync ({prov}): "
                          f"{r['inserted']} inserted, {r['refreshed']} refreshed, "
                          f"{r['deactivated']} deactivated.", flush=True)
        finally:
            conn.close()
    except Exception as e:
        print(f"[remote-models] startup sync FAILED: {e!r}", flush=True)
    finally:
        if str(scripts_dir) in _sys.path:
            _sys.path.remove(str(scripts_dir))
