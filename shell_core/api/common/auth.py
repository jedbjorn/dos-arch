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
    """Admin-only ops. An API-key shell is never an admin caller; the UI is."""
    if _caller_shell(request) is not None:
        raise HTTPException(403, "API-key callers may not perform admin operations.")


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
