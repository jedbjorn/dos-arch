"""Auth helpers — tenant scoping for shell-private surfaces.

Two caller identities flow off `request.state` (set by `auth_passthrough`):
a **user session** resolves `user_id` (+ `is_admin`); a shell's **substrate-API
key** resolves `shell_id` (+ `shell_is_admin`). The dispatcher carries each
shell's own key, so a shell-key caller always acts as that shell.

The `_require_shell_*` gates below enforce the data-isolation spec's
**user-private** class (`docs/specs/data-isolation.md`, CC-108): a shell's seed /
L&S / decisions / archives / chat / current_state are reachable only by the
shell itself (its key), its owning user, or the operator (admin) backstop.
Denial is always **404, never 403** — a 403 would confirm the row exists."""

from fastapi import HTTPException, Request


def _caller_shell(request: Request) -> int | None:
    """The shell_id of an API-key caller, or None for a user-session caller."""
    return getattr(request.state, "shell_id", None)


def _is_shell_owner(row, request: Request) -> bool:
    """True iff the caller owns this shell row outright (not via is_shared):
    the shell's own key, an admin shell, the owning user, or an admin user.
    `row` must expose `shell_id` and `user_id`. Used to decide whether the
    private columns of an otherwise-visible card may be returned."""
    caller_shell = _caller_shell(request)
    if caller_shell is not None:
        return caller_shell == row["shell_id"] or getattr(request.state, "shell_is_admin", False)
    uid = getattr(request.state, "user_id", None)
    if uid is None:
        return False
    return row["user_id"] == uid or getattr(request.state, "is_admin", False)


def _shell_access(shell_id: int, request: Request, con, *, allow_shared: bool):
    """Core tenant gate for a shell-scoped surface. Returns the shell row
    (`shell_id`, `user_id`, `is_shared`) or raises 404. Access if any of:
      - api-key caller is this shell, or is an admin shell;
      - a user session owns the shell (`shells.user_id == user_id`);
      - the session user is an admin (operator/root backstop);
      - `allow_shared` and the shell is `is_shared` (global infra — card/prompt
        reads only; never private-mind writes).
    404 (not 403) on every denial so existence is not confirmed."""
    row = con.execute(
        "SELECT shell_id, user_id, is_shared FROM shells WHERE shell_id=?", (shell_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Shell not found")
    caller_shell = _caller_shell(request)
    if caller_shell is not None:
        if caller_shell == shell_id or getattr(request.state, "shell_is_admin", False):
            return row
        # An api-key shell may still read a shared shell's card/prompt (Global
        # class) — but never its private mind (allow_shared=False).
        if allow_shared and row["is_shared"]:
            return row
        raise HTTPException(404, "Shell not found")
    uid = getattr(request.state, "user_id", None)
    if uid is not None and (row["user_id"] == uid or getattr(request.state, "is_admin", False)):
        return row
    if allow_shared and row["is_shared"]:
        return row
    raise HTTPException(404, "Shell not found")


def _require_shell_owner(shell_id: int, request: Request, con):
    """Private-mind surfaces (seed/L&S, decisions, archives, chat, sessions,
    current_state) + any mutation: owner / shell-self / admin only. NOT
    readable via is_shared — a shared shell's mind is still its own."""
    return _shell_access(shell_id, request, con, allow_shared=False)


def _require_shell_visible(shell_id: int, request: Request, con):
    """Card / prompt surfaces: owner / shell-self / admin, plus is_shared
    system shells (the Global visibility class)."""
    return _shell_access(shell_id, request, con, allow_shared=True)


def _require_archive_owner(archive_id: int, request: Request, con) -> int:
    """Owner-gate an archive addressed by its archive_id: resolve the owning
    shell, then apply `_require_shell_owner`. Returns the shell_id. 404 if the
    archive does not exist or is not the caller's."""
    arow = con.execute(
        "SELECT shell_id FROM shell_memory_archives WHERE archive_id=?", (archive_id,)
    ).fetchone()
    if arow is None:
        raise HTTPException(404, "Archive not found")
    _require_shell_owner(arow["shell_id"], request, con)
    return arow["shell_id"]


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
