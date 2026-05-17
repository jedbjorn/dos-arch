from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.routing import Match
import hashlib
import time

from api.common.db import db
from api.common.logging import _log_action
from api.common.errors import _log_5xx

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


def _resolve_caller_shell(request: Request) -> tuple[int | None, str | None, bool]:
    """Resolve an API-key token to a shell. Returns (shell_id, shortname, bad);
    `bad` is True when a token was presented but matched no shell. No token at
    all → (None, None, False)."""
    token = ""
    authz = request.headers.get("authorization", "")
    if authz[:7].lower() == "bearer ":
        token = authz[7:].strip()
    if not token:
        token = (request.query_params.get("api_key") or "").strip()
    if not token:
        return None, None, False
    digest = hashlib.sha256(token.encode()).hexdigest()
    con = db()
    try:
        row = con.execute(
            "SELECT shell_id, shortname FROM shells WHERE api_key_hash=?", (digest,)
        ).fetchone()
    finally:
        con.close()
    if row is None:
        return None, None, True
    return row["shell_id"], row["shortname"], False


@app.middleware("http")
async def auth_passthrough(request: Request, call_next):
    request.state.user_id   = 1
    request.state.is_admin  = True
    shell_id, shell_name, bad = _resolve_caller_shell(request)
    if bad:
        return JSONResponse(status_code=401, content={"detail": "Invalid API key."})
    request.state.shell_id   = shell_id
    request.state.shell_name = shell_name
    t0 = time.monotonic()
    response = await call_next(request)
    if request.method in MUTATION_METHODS:
        duration = int((time.monotonic() - t0) * 1000)
        ip = request.client.host if request.client else "unknown"
        _log_action(request.method, request.url.path, response.status_code, duration, ip, user_id=1)
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

from api.routers.flags import router as flags_router
app.include_router(flags_router)

from api.routers.admin import router as admin_router
app.include_router(admin_router)


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
        from dr_sync import sync_all  # type: ignore[import-not-found]
        conn = sqlite3.connect(db_path)
        try:
            results = sync_all(conn, app=app)
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
