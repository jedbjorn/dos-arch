"""/emails — correspondence with a contact, project-team scoped (CC-108).

An email files under **one** project (`emails.project_id`), seeded from the
contact's default at creation and re-fileable after. Visibility is membership in
that single project — which is what produces the spec's *compartmentalization*:
a contact is N:M to projects, but each email files under one, so the contact
*card* can be broader than any one conversation about them. You can see *who* a
contact is (via a shared project) without seeing *every* email (filed under
projects you are not in).

Same shape as contacts/flags: the membership predicate composed into every read,
a membership assert on the filing project, 404-not-403.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api.common.db import get_db
from api.common.tenancy import assert_member, my_projects_subquery
from api.routers.contacts import _visible_contact

router = APIRouter(tags=["emails"])

_DIRECTIONS = ("inbound", "outbound")


def _visible_email(con, request: Request, email_id: int, cols: str = "e.*"):
    """The email row iff it exists, is live, AND the caller is a member of the
    project it is filed under. None → the caller turns it into a 404."""
    sub, params = my_projects_subquery(request)
    return con.execute(
        f"SELECT {cols} FROM emails e "
        f"WHERE e.email_id = ? AND e.is_deleted = 0 AND e.project_id IN ({sub})",
        (email_id, *params),
    ).fetchone()


class CreateEmailBody(BaseModel):
    contact_id:  int
    project_id:  int | None = None     # defaults to the contact's default project
    direction:   str | None = None     # 'inbound' | 'outbound'
    subject:     str | None = None
    body:        str | None = None
    occurred_at: str | None = None
    message_id:  str | None = None
    thread_id:   str | None = None


class UpdateEmailBody(BaseModel):
    project_id:  int | None = None     # re-file under a different project
    direction:   str | None = None
    subject:     str | None = None
    body:        str | None = None
    occurred_at: str | None = None
    thread_id:   str | None = None


def _check_direction(d):
    if d is not None and d not in _DIRECTIONS:
        raise HTTPException(422, f"direction must be one of {_DIRECTIONS}")


@router.post("/emails", summary="Record an email with a visible contact, filed under a member project")
def create_email(body: CreateEmailBody, request: Request, con = Depends(get_db)):
    # The contact must be visible to the caller (member of one of its projects).
    contact = _visible_contact(con, request, body.contact_id,
                               cols="c.contact_id, c.default_project_id")
    if not contact:
        raise HTTPException(404, "Contact not found")
    _check_direction(body.direction)
    # File under the given project, or the contact's default. Either way the
    # caller must be a member of the filing project (404 if not).
    project_id = body.project_id if body.project_id is not None else contact["default_project_id"]
    if project_id is None:
        raise HTTPException(422, "project_id is required — the contact has no default project")
    assert_member(con, request, project_id)

    cur = con.execute(
        "INSERT INTO emails (contact_id, project_id, direction, subject, body, "
        "occurred_at, message_id, thread_id) VALUES (?,?,?,?,?,?,?,?)",
        (body.contact_id, project_id, body.direction, body.subject, body.body,
         body.occurred_at, body.message_id, body.thread_id),
    )
    con.commit()
    return _email_dict(con, cur.lastrowid)


@router.get("/emails", summary="List emails the caller can see (member of the filing project)")
def list_emails(request: Request, contact_id: int | None = None,
                project_id: int | None = None, thread_id: str = "", con = Depends(get_db)):
    sub, params = my_projects_subquery(request)
    where = ["e.is_deleted = 0", f"e.project_id IN ({sub})"]
    args = list(params)
    if contact_id is not None:
        where.append("e.contact_id = ?"); args.append(contact_id)
    if project_id is not None:
        assert_member(con, request, project_id)
        where.append("e.project_id = ?"); args.append(project_id)
    if thread_id:
        where.append("e.thread_id = ?"); args.append(thread_id)
    rows = con.execute(
        f"SELECT e.* FROM emails e WHERE {' AND '.join(where)} "
        f"ORDER BY COALESCE(e.occurred_at, e.created_at) DESC, e.email_id DESC",
        args,
    ).fetchall()
    return {"count": len(rows), "emails": [dict(r) for r in rows]}


@router.get("/emails/{email_id}", summary="Get one visible email")
def get_email(email_id: int, request: Request, con = Depends(get_db)):
    row = _visible_email(con, request, email_id)
    if not row:
        raise HTTPException(404, "Email not found")
    return dict(row)


@router.patch("/emails/{email_id}", summary="Update or re-file a visible email")
def update_email(email_id: int, body: UpdateEmailBody, request: Request, con = Depends(get_db)):
    if not _visible_email(con, request, email_id, cols="1"):
        raise HTTPException(404, "Email not found")
    _check_direction(body.direction)
    fields, args = [], []
    if body.project_id is not None:
        # Re-filing: the caller must be a member of the destination project too.
        assert_member(con, request, body.project_id)
        fields.append("project_id = ?"); args.append(body.project_id)
    for col in ("direction", "subject", "body", "occurred_at", "thread_id"):
        val = getattr(body, col)
        if val is not None:
            fields.append(f"{col} = ?"); args.append(val)
    if fields:
        args.append(email_id)
        con.execute(f"UPDATE emails SET {', '.join(fields)} WHERE email_id = ?", args)
        con.commit()
    return _email_dict(con, email_id)


@router.delete("/emails/{email_id}", summary="Soft-delete a visible email")
def delete_email(email_id: int, request: Request, con = Depends(get_db)):
    if not _visible_email(con, request, email_id, cols="1"):
        raise HTTPException(404, "Email not found")
    con.execute("UPDATE emails SET is_deleted = 1 WHERE email_id = ?", (email_id,))
    con.commit()
    return {"ok": True, "email_id": email_id}


def _email_dict(con, email_id: int) -> dict:
    return dict(con.execute("SELECT * FROM emails WHERE email_id = ?", (email_id,)).fetchone())
