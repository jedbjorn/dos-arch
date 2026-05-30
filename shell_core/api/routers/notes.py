"""/notes — the unified annotation feed, scoped by its target (CC-108).

A note has an **exclusive arc**: exactly one target per kind (contact / event /
project / user), enforced by a DB CHECK (core-data-model). Visibility *derives
from the target*:

  - project target → member of that project
  - contact target → visible iff the contact is (member of any of its projects)
  - event target   → visible iff the event is (member of any of its projects)
  - **user target → author-private** (the parked classification, resolved here)

The user-target case (`kind='note'` with `user_id`) is a note *about a person*
and has no project to derive visibility from. It is therefore **owner-only**:
visible to its `author_user_id` (and the operator/admin) and nobody else — the
safe, leak-free resolution. The author is always the resolved session user, not
a client field.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api.common.db import get_db
from api.routers.contacts import _visible_contact
from api.routers.events import _visible_event

router = APIRouter(tags=["notes"])

_KINDS = ("note", "document", "meeting_prep", "meeting_result")
_TARGETS = ("contact_id", "event_id", "project_id", "user_id")


def _is_member(con, request: Request, project_id: int) -> bool:
    uid = getattr(request.state, "user_id", None)
    return bool(con.execute(
        "SELECT 1 FROM user_projects WHERE user_id = ? AND project_id = ? AND is_deleted = 0",
        (uid, project_id)).fetchone())


def _note_is_visible(con, request: Request, n) -> bool:
    """Visibility derives from the note's single target (see module docstring).
    The operator (admin user) is a backstop for the author-private user-target."""
    uid = getattr(request.state, "user_id", None)
    if n["project_id"] is not None:
        return _is_member(con, request, n["project_id"])
    if n["contact_id"] is not None:
        return _visible_contact(con, request, n["contact_id"], cols="1") is not None
    if n["event_id"] is not None:
        return _visible_event(con, request, n["event_id"], cols="1") is not None
    if n["user_id"] is not None:
        # Author-private: only the author (or the admin backstop) sees it.
        return uid is not None and (n["author_user_id"] == uid
                                    or getattr(request.state, "is_admin", False))
    return False


def _visible_note(con, request: Request, note_id: int):
    n = con.execute("SELECT * FROM notes WHERE note_id = ? AND is_deleted = 0", (note_id,)).fetchone()
    if not n or not _note_is_visible(con, request, n):
        return None
    return n


class CreateNoteBody(BaseModel):
    kind:       str
    body:       str | None = None
    contact_id: int | None = None
    event_id:   int | None = None
    project_id: int | None = None
    user_id:    int | None = None
    doc_url:    str | None = None
    doc_mime:   str | None = None
    doc_size:   int | None = None


class UpdateNoteBody(BaseModel):
    body:     str | None = None
    doc_url:  str | None = None
    doc_mime: str | None = None
    doc_size: int | None = None


def _validate_kind_target(kind: str, body: CreateNoteBody) -> None:
    """Enforce the kind→target matrix in-app (the DB CHECK is the backstop)."""
    if kind not in _KINDS:
        raise HTTPException(422, f"kind must be one of {_KINDS}")
    set_targets = [t for t in _TARGETS if getattr(body, t) is not None]
    if kind == "note":
        if len(set_targets) != 1:
            raise HTTPException(422, "a 'note' targets exactly one of contact/event/project/user")
    elif kind == "document":
        if set_targets not in (["event_id"], ["project_id"]):
            raise HTTPException(422, "a 'document' targets exactly one of event/project")
    else:  # meeting_prep / meeting_result
        if set_targets != ["event_id"]:
            raise HTTPException(422, f"a '{kind}' targets an event only")


def _assert_target_visible(con, request: Request, body: CreateNoteBody) -> None:
    """The caller must be able to *see* the note's target before annotating it.
    A user target is author-private, so it needs no membership — the caller is
    recording their own note about that person."""
    if body.project_id is not None and not _is_member(con, request, body.project_id):
        raise HTTPException(404, "Project not found")
    if body.contact_id is not None and not _visible_contact(con, request, body.contact_id, cols="1"):
        raise HTTPException(404, "Contact not found")
    if body.event_id is not None and not _visible_event(con, request, body.event_id, cols="1"):
        raise HTTPException(404, "Event not found")


@router.post("/notes", summary="Add a note to a target you can see (author = the session user)")
def create_note(body: CreateNoteBody, request: Request, con = Depends(get_db)):
    author = getattr(request.state, "user_id", None)
    if author is None:
        raise HTTPException(404, "Not found")        # unauthenticated — closed by default
    _validate_kind_target(body.kind, body)
    _assert_target_visible(con, request, body)
    try:
        cur = con.execute(
            "INSERT INTO notes (kind, body, author_user_id, contact_id, event_id, project_id, "
            "user_id, doc_url, doc_mime, doc_size) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (body.kind, body.body, author, body.contact_id, body.event_id, body.project_id,
             body.user_id, body.doc_url, body.doc_mime, body.doc_size),
        )
    except Exception:
        con.rollback()
        raise HTTPException(422, "note violates the kind/target constraint")
    con.commit()
    return dict(con.execute("SELECT * FROM notes WHERE note_id = ?", (cur.lastrowid,)).fetchone())


@router.get("/notes", summary="List notes on a visible target")
def list_notes(request: Request, contact_id: int | None = None, event_id: int | None = None,
               project_id: int | None = None, con = Depends(get_db)):
    """Scoped to one target the caller can see — the common access path (a
    contact's / event's / project's feed). At least one target filter is
    required; the caller must be able to see it (404 otherwise)."""
    if project_id is not None:
        if not _is_member(con, request, project_id):
            raise HTTPException(404, "Project not found")
        where, arg = "project_id = ?", project_id
    elif contact_id is not None:
        if not _visible_contact(con, request, contact_id, cols="1"):
            raise HTTPException(404, "Contact not found")
        where, arg = "contact_id = ?", contact_id
    elif event_id is not None:
        if not _visible_event(con, request, event_id, cols="1"):
            raise HTTPException(404, "Event not found")
        where, arg = "event_id = ?", event_id
    else:
        raise HTTPException(422, "one of project_id / contact_id / event_id is required")
    rows = con.execute(
        f"SELECT * FROM notes WHERE is_deleted = 0 AND {where} ORDER BY created_at, note_id",
        (arg,),
    ).fetchall()
    return {"count": len(rows), "notes": [dict(r) for r in rows]}


@router.get("/notes/{note_id}", summary="Get one visible note")
def get_note(note_id: int, request: Request, con = Depends(get_db)):
    n = _visible_note(con, request, note_id)
    if not n:
        raise HTTPException(404, "Note not found")
    return dict(n)


@router.patch("/notes/{note_id}", summary="Edit a visible note's body / document fields")
def update_note(note_id: int, body: UpdateNoteBody, request: Request, con = Depends(get_db)):
    if not _visible_note(con, request, note_id):
        raise HTTPException(404, "Note not found")
    fields, args = [], []
    for col in ("body", "doc_url", "doc_mime", "doc_size"):
        val = getattr(body, col)
        if val is not None:
            fields.append(f"{col} = ?"); args.append(val)
    if fields:
        con.execute(f"UPDATE notes SET {', '.join(fields)} WHERE note_id = ?", (*args, note_id))
        con.commit()
    return dict(con.execute("SELECT * FROM notes WHERE note_id = ?", (note_id,)).fetchone())


@router.delete("/notes/{note_id}", summary="Soft-delete a visible note")
def delete_note(note_id: int, request: Request, con = Depends(get_db)):
    if not _visible_note(con, request, note_id):
        raise HTTPException(404, "Note not found")
    con.execute("UPDATE notes SET is_deleted = 1 WHERE note_id = ?", (note_id,))
    con.commit()
    return {"ok": True, "note_id": note_id}
