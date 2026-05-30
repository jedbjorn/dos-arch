"""/contacts — external people, project-team scoped (CC-108, data-isolation).

The first domain router. Contacts are **project-team** data (core-data-model):
a contact is N:M to projects via `contact_projects`, and is visible to anyone
who is a member of *any* project it is filed under. This module copies the
`flags.py` reference shape — one visibility predicate composed into every read,
mutations gated through a visible-row lookup (404, never 403), and a membership
assert on the project a row is filed under at create time.

The caller's `user_id` is resolved by the middleware from the session (or, for
an api-key shell, the substrate owner). The client never supplies it.

Location fields are stored as given for now; the geocoding/normalization service
(core-data-model open question) is not wired in here.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.common.db import get_db

router = APIRouter(tags=["contacts"])


# ── Visibility (project-team via contact_projects N:M) ────────────────────────
# A contact is visible iff the caller is a member of at least one project the
# contact is filed under. An unauthenticated caller resolves user_id=None, so the
# membership subquery is empty and nothing matches — closed by default.

def _membership_subquery(request: Request) -> tuple[str, list]:
    uid = getattr(request.state, "user_id", None)
    return ("SELECT project_id FROM user_projects "
            "WHERE user_id = ? AND is_deleted = 0", [uid])


def _visible_contact(con, request: Request, contact_id: int, cols: str = "c.*"):
    """The contact row (selected cols) iff it exists, is live, AND the caller is
    a member of one of its projects. None otherwise — callers turn that into a
    404 so 'not yours' is indistinguishable from 'does not exist'."""
    sub, params = _membership_subquery(request)
    return con.execute(
        f"SELECT {cols} FROM contacts c "
        f"WHERE c.contact_id = ? AND c.is_deleted = 0 "
        f"AND EXISTS (SELECT 1 FROM contact_projects cp "
        f"            WHERE cp.contact_id = c.contact_id AND cp.is_deleted = 0 "
        f"            AND cp.project_id IN ({sub}))",
        (contact_id, *params),
    ).fetchone()


def _assert_member(con, request: Request, project_id: int) -> None:
    """The caller must be a member of `project_id` to file a contact under it.
    404 (not 403) — don't confirm the project exists to a non-member."""
    uid = getattr(request.state, "user_id", None)
    if not con.execute(
        "SELECT 1 FROM user_projects WHERE user_id = ? AND project_id = ? AND is_deleted = 0",
        (uid, project_id),
    ).fetchone():
        raise HTTPException(404, "Project not found")


_LOCATION_FIELDS = ("formatted_address", "locality", "region", "country",
                    "postal_code", "lat", "lng")


# ── Models ────────────────────────────────────────────────────────────────────

class CreateContactBody(BaseModel):
    name:               str
    email:              str | None = None
    phone:              str | None = None
    formatted_address:  str | None = None
    locality:           str | None = None
    region:             str | None = None
    country:            str | None = None
    postal_code:        str | None = None
    lat:                float | None = None
    lng:                float | None = None
    project_ids:        list[int] = Field(default_factory=list)
    default_project_id: int | None = None


class UpdateContactBody(BaseModel):
    name:               str | None = None
    email:              str | None = None
    phone:              str | None = None
    formatted_address:  str | None = None
    locality:           str | None = None
    region:             str | None = None
    country:            str | None = None
    postal_code:        str | None = None
    lat:                float | None = None
    lng:                float | None = None
    default_project_id: int | None = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/contacts", summary="Create a contact filed under one or more of the caller's projects")
def create_contact(body: CreateContactBody, request: Request, con = Depends(get_db)):
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "name is required")
    project_ids = list(dict.fromkeys(body.project_ids))  # de-dup, keep order
    if not project_ids:
        raise HTTPException(422, "project_ids is required — a contact must be filed under a project")
    # Membership is the access axis: you may only file a contact under projects
    # you have joined. Assert every one before writing anything.
    for pid in project_ids:
        _assert_member(con, request, pid)
    default_pid = body.default_project_id
    if default_pid is not None and default_pid not in project_ids:
        raise HTTPException(422, "default_project_id must be one of project_ids")
    if default_pid is None:
        default_pid = project_ids[0]

    cur = con.execute(
        "INSERT INTO contacts (name, email, phone, formatted_address, locality, region, "
        "country, postal_code, lat, lng, default_project_id) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (name, body.email, body.phone, body.formatted_address, body.locality, body.region,
         body.country, body.postal_code, body.lat, body.lng, default_pid),
    )
    contact_id = cur.lastrowid
    con.executemany(
        "INSERT INTO contact_projects (contact_id, project_id) VALUES (?, ?)",
        [(contact_id, pid) for pid in project_ids],
    )
    con.commit()
    return _contact_dict(con, contact_id)


@router.get("/contacts", summary="List contacts visible to the caller (member of any filed project)")
def list_contacts(request: Request, project_id: int | None = None, q: str = "", con = Depends(get_db)):
    sub, params = _membership_subquery(request)
    where = ["c.is_deleted = 0",
             f"EXISTS (SELECT 1 FROM contact_projects cp WHERE cp.contact_id = c.contact_id "
             f"AND cp.is_deleted = 0 AND cp.project_id IN ({sub}))"]
    args = list(params)
    if project_id is not None:
        # Scope to one project — but only if the caller is a member of it.
        _assert_member(con, request, project_id)
        where.append("EXISTS (SELECT 1 FROM contact_projects cp2 WHERE cp2.contact_id = c.contact_id "
                     "AND cp2.is_deleted = 0 AND cp2.project_id = ?)")
        args.append(project_id)
    if q:
        where.append("(c.name LIKE ? OR c.email LIKE ?)")
        args.extend([f"%{q}%", f"%{q}%"])
    rows = con.execute(
        f"SELECT c.* FROM contacts c WHERE {' AND '.join(where)} ORDER BY c.name, c.contact_id",
        args,
    ).fetchall()
    return {"count": len(rows), "contacts": [_with_projects(con, dict(r)) for r in rows]}


@router.get("/contacts/{contact_id}", summary="Get one visible contact")
def get_contact(contact_id: int, request: Request, con = Depends(get_db)):
    if not _visible_contact(con, request, contact_id, cols="1"):
        raise HTTPException(404, "Contact not found")
    return _contact_dict(con, contact_id)


@router.patch("/contacts/{contact_id}", summary="Update a visible contact's fields")
def update_contact(contact_id: int, body: UpdateContactBody, request: Request, con = Depends(get_db)):
    if not _visible_contact(con, request, contact_id, cols="1"):
        raise HTTPException(404, "Contact not found")
    fields, args = [], []
    if body.name is not None:
        if not body.name.strip():
            raise HTTPException(422, "name cannot be empty")
        fields.append("name = ?"); args.append(body.name.strip())
    for col in ("email", "phone", *_LOCATION_FIELDS):
        val = getattr(body, col)
        if val is not None:
            fields.append(f"{col} = ?"); args.append(val)
    if body.default_project_id is not None:
        # The new default must be a project the contact is actually filed under.
        if not con.execute(
            "SELECT 1 FROM contact_projects WHERE contact_id = ? AND project_id = ? AND is_deleted = 0",
            (contact_id, body.default_project_id),
        ).fetchone():
            raise HTTPException(422, "default_project_id must be one of the contact's projects")
        fields.append("default_project_id = ?"); args.append(body.default_project_id)
    if fields:
        args.append(contact_id)
        con.execute(f"UPDATE contacts SET {', '.join(fields)} WHERE contact_id = ?", args)
        con.commit()
    return _contact_dict(con, contact_id)


@router.delete("/contacts/{contact_id}", summary="Soft-delete a visible contact")
def delete_contact(contact_id: int, request: Request, con = Depends(get_db)):
    if not _visible_contact(con, request, contact_id, cols="1"):
        raise HTTPException(404, "Contact not found")
    con.execute("UPDATE contacts SET is_deleted = 1 WHERE contact_id = ?", (contact_id,))
    con.execute("UPDATE contact_projects SET is_deleted = 1 WHERE contact_id = ?", (contact_id,))
    con.commit()
    return {"ok": True, "contact_id": contact_id}


# ── Serialization ─────────────────────────────────────────────────────────────

def _project_ids(con, contact_id: int) -> list[int]:
    return [r["project_id"] for r in con.execute(
        "SELECT project_id FROM contact_projects WHERE contact_id = ? AND is_deleted = 0 "
        "ORDER BY project_id", (contact_id,))]


def _with_projects(con, d: dict) -> dict:
    d["project_ids"] = _project_ids(con, d["contact_id"])
    return d


def _contact_dict(con, contact_id: int) -> dict:
    row = con.execute("SELECT * FROM contacts WHERE contact_id = ?", (contact_id,)).fetchone()
    return _with_projects(con, dict(row))
