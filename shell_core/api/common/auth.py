"""Auth helpers — substrate-API-key scoping.

The HTTP surface stays single-user (every request is user_id=1). When a shell
authenticates with its substrate-API key, the `auth_passthrough` middleware
sets `request.state.shell_id`; these helpers then scope that shell to its own
records. A request with no API key (the localhost UI) has `shell_id=None` and
keeps full access — unchanged from the phase-3 passthrough."""

from fastapi import HTTPException, Request


def _caller_shell(request: Request) -> int | None:
    """The shell_id of an API-key caller, or None for the unauthenticated UI."""
    return getattr(request.state, "shell_id", None)


def _require_admin(request: Request) -> None:
    """Admin-only ops. An API-key caller must be an admin shell (is_admin=1).
    Otherwise the caller is a user session (or, in Phase 1, the legacy keyless
    UI): require `is_admin`, which the middleware resolves from the session user
    — a logged-in non-admin is refused. (The legacy keyless default is is_admin
    =True until Phase 2 flips the keyless case to unauthenticated.)"""
    if _caller_shell(request) is not None:
        if not getattr(request.state, "shell_is_admin", False):
            raise HTTPException(403, "This shell is not an admin shell.")
        return
    if not getattr(request.state, "is_admin", False):
        raise HTTPException(403, "Admin only.")


def _require_shell_creator(request: Request, con) -> None:
    """Creating a shell: allowed for the keyless localhost UI, an admin shell
    (Sys-Admin), or a shared bootstrap shell (Forge, is_shared=1). Every other
    API-key caller — the worker shells — is refused."""
    caller = _caller_shell(request)
    if caller is None:
        return  # the localhost UI
    row = con.execute(
        "SELECT is_admin, is_shared FROM shells WHERE shell_id=?", (caller,)
    ).fetchone()
    if not row or not (row["is_admin"] or row["is_shared"]):
        raise HTTPException(403, "Only Forge or an admin shell may create shells.")


def _require_shell_self(shell_id: int, request: Request) -> None:
    """An API-key shell may act only on its own shell_id."""
    caller = _caller_shell(request)
    if caller is not None and caller != shell_id:
        raise HTTPException(
            403, f"API key is scoped to shell {caller}, not shell {shell_id}."
        )


def _require_shell_self_or_paired_user(shell_id: int, request: Request, con) -> None:
    # Single-user substrate: the "paired user" is always user 1, so this
    # reduces to the self-scope check — an API-key shell must be acting on
    # itself; the UI (no key) is unrestricted.
    _require_shell_self(shell_id, request)


def _resolve_caller_staff_id(request: Request, con) -> int:
    return 1
