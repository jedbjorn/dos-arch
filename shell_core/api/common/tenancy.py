"""Shared project-membership helpers for domain routers (CC-108).

The project is the access spine: **project-team** data is visible to members of
the relevant project (`user_projects`). These helpers centralize the one
membership predicate so every domain router — contacts, emails, events, notes —
composes the *same* SQL, with no per-router drift.

The caller's `user_id` is resolved by the middleware from the session (or, for
an api-key shell, the substrate owner); the client never supplies it. An
unauthenticated caller resolves `None`, so the subquery is empty and matches
nothing — project-team reads are closed by default.
"""
from fastapi import HTTPException, Request


def my_projects_subquery(request: Request) -> tuple[str, list]:
    """`(sql, params)` for *the projects the caller has joined* — compose it into
    a `... project_id IN ({sub})` clause."""
    uid = getattr(request.state, "user_id", None)
    return ("SELECT project_id FROM user_projects WHERE user_id = ? AND is_deleted = 0", [uid])


def assert_member(con, request: Request, project_id: int) -> None:
    """Raise 404 (never 403 — don't confirm existence to a non-member) unless the
    caller is a member of `project_id`. Used before filing a row under a project."""
    uid = getattr(request.state, "user_id", None)
    if not con.execute(
        "SELECT 1 FROM user_projects WHERE user_id = ? AND project_id = ? AND is_deleted = 0",
        (uid, project_id),
    ).fetchone():
        raise HTTPException(404, "Project not found")
