"""/events — calendar events, project-team scoped (CC-108).

An event is N:M to projects (`event_projects`, one row flagged `is_primary` =
the editable "default" project), and N:M to contacts and users. Visibility is
membership in **any** of the event's projects — the same N:M shape as contacts.
A contact attached to an event must itself be visible to the caller; project
filing is membership-asserted. 404-not-403 throughout.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.common.db import get_db
from api.common.tenancy import assert_member, my_projects_subquery
from api.routers.contacts import _visible_contact

router = APIRouter(tags=["events"])

_LOCATION_FIELDS = ("formatted_address", "locality", "region", "country",
                    "postal_code", "lat", "lng")


def _visible_event(con, request: Request, event_id: int, cols: str = "e.*"):
    """The event row iff it exists, is live, AND the caller is a member of one of
    its projects. None → 404 at the call site."""
    sub, params = my_projects_subquery(request)
    return con.execute(
        f"SELECT {cols} FROM events e "
        f"WHERE e.event_id = ? AND e.is_deleted = 0 "
        f"AND EXISTS (SELECT 1 FROM event_projects ep "
        f"            WHERE ep.event_id = e.event_id AND ep.project_id IN ({sub}))",
        (event_id, *params),
    ).fetchone()


class CreateEventBody(BaseModel):
    title:              str
    start_at:           str | None = None
    end_at:             str | None = None
    formatted_address:  str | None = None
    locality:           str | None = None
    region:             str | None = None
    country:            str | None = None
    postal_code:        str | None = None
    lat:                float | None = None
    lng:                float | None = None
    project_ids:        list[int] = Field(default_factory=list)
    primary_project_id: int | None = None
    contact_ids:        list[int] = Field(default_factory=list)
    user_ids:           list[int] = Field(default_factory=list)


class UpdateEventBody(BaseModel):
    title:              str | None = None
    start_at:           str | None = None
    end_at:             str | None = None
    formatted_address:  str | None = None
    locality:           str | None = None
    region:             str | None = None
    country:            str | None = None
    postal_code:        str | None = None
    lat:                float | None = None
    lng:                float | None = None
    primary_project_id: int | None = None   # must be one of the event's projects


@router.post("/events", summary="Create an event filed under one or more of the caller's projects")
def create_event(body: CreateEventBody, request: Request, con = Depends(get_db)):
    title = body.title.strip()
    if not title:
        raise HTTPException(422, "title is required")
    project_ids = list(dict.fromkeys(body.project_ids))
    if not project_ids:
        raise HTTPException(422, "project_ids is required — an event must be filed under a project")
    for pid in project_ids:
        assert_member(con, request, pid)
    primary = body.primary_project_id
    if primary is not None and primary not in project_ids:
        raise HTTPException(422, "primary_project_id must be one of project_ids")
    if primary is None:
        primary = project_ids[0]
    # Any attached contact must be visible to the caller.
    contact_ids = list(dict.fromkeys(body.contact_ids))
    for cid in contact_ids:
        if not _visible_contact(con, request, cid, cols="1"):
            raise HTTPException(404, "Contact not found")
    user_ids = list(dict.fromkeys(body.user_ids))

    cols = ["title", "start_at", "end_at", *_LOCATION_FIELDS]
    vals = [title, body.start_at, body.end_at] + [getattr(body, c) for c in _LOCATION_FIELDS]
    cur = con.execute(
        f"INSERT INTO events ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", vals)
    event_id = cur.lastrowid
    con.executemany(
        "INSERT INTO event_projects (event_id, project_id, is_primary) VALUES (?,?,?)",
        [(event_id, pid, 1 if pid == primary else 0) for pid in project_ids])
    if contact_ids:
        con.executemany("INSERT INTO event_contacts (event_id, contact_id) VALUES (?,?)",
                        [(event_id, cid) for cid in contact_ids])
    if user_ids:
        try:
            con.executemany("INSERT INTO event_users (event_id, user_id) VALUES (?,?)",
                            [(event_id, uid) for uid in user_ids])
        except Exception:
            con.rollback()
            raise HTTPException(422, "one or more user_ids do not exist")
    con.commit()
    return _event_dict(con, event_id)


@router.get("/events", summary="List events the caller can see (member of any of the event's projects)")
def list_events(request: Request, project_id: int | None = None, con = Depends(get_db)):
    sub, params = my_projects_subquery(request)
    where = ["e.is_deleted = 0",
             f"EXISTS (SELECT 1 FROM event_projects ep WHERE ep.event_id = e.event_id "
             f"AND ep.project_id IN ({sub}))"]
    args = list(params)
    if project_id is not None:
        assert_member(con, request, project_id)
        where.append("EXISTS (SELECT 1 FROM event_projects ep2 WHERE ep2.event_id = e.event_id "
                     "AND ep2.project_id = ?)")
        args.append(project_id)
    rows = con.execute(
        f"SELECT e.* FROM events e WHERE {' AND '.join(where)} "
        f"ORDER BY COALESCE(e.start_at, e.created_at), e.event_id",
        args,
    ).fetchall()
    return {"count": len(rows), "events": [_with_links(con, dict(r)) for r in rows]}


@router.get("/events/{event_id}", summary="Get one visible event")
def get_event(event_id: int, request: Request, con = Depends(get_db)):
    if not _visible_event(con, request, event_id, cols="1"):
        raise HTTPException(404, "Event not found")
    return _event_dict(con, event_id)


@router.patch("/events/{event_id}", summary="Update a visible event's fields / primary project")
def update_event(event_id: int, body: UpdateEventBody, request: Request, con = Depends(get_db)):
    if not _visible_event(con, request, event_id, cols="1"):
        raise HTTPException(404, "Event not found")
    fields, args = [], []
    if body.title is not None:
        if not body.title.strip():
            raise HTTPException(422, "title cannot be empty")
        fields.append("title = ?"); args.append(body.title.strip())
    for col in ("start_at", "end_at", *_LOCATION_FIELDS):
        val = getattr(body, col)
        if val is not None:
            fields.append(f"{col} = ?"); args.append(val)
    if fields:
        con.execute(f"UPDATE events SET {', '.join(fields)} WHERE event_id = ?", (*args, event_id))
    if body.primary_project_id is not None:
        # The new primary must already be one of the event's projects.
        if not con.execute(
            "SELECT 1 FROM event_projects WHERE event_id = ? AND project_id = ?",
            (event_id, body.primary_project_id),
        ).fetchone():
            raise HTTPException(422, "primary_project_id must be one of the event's projects")
        con.execute("UPDATE event_projects SET is_primary = 0 WHERE event_id = ?", (event_id,))
        con.execute("UPDATE event_projects SET is_primary = 1 WHERE event_id = ? AND project_id = ?",
                    (event_id, body.primary_project_id))
    con.commit()
    return _event_dict(con, event_id)


@router.delete("/events/{event_id}", summary="Soft-delete a visible event")
def delete_event(event_id: int, request: Request, con = Depends(get_db)):
    if not _visible_event(con, request, event_id, cols="1"):
        raise HTTPException(404, "Event not found")
    con.execute("UPDATE events SET is_deleted = 1 WHERE event_id = ?", (event_id,))
    con.commit()
    return {"ok": True, "event_id": event_id}


# ── Serialization ─────────────────────────────────────────────────────────────

def _with_links(con, d: dict) -> dict:
    eid = d["event_id"]
    d["project_ids"] = [r["project_id"] for r in con.execute(
        "SELECT project_id FROM event_projects WHERE event_id = ? ORDER BY project_id", (eid,))]
    prow = con.execute(
        "SELECT project_id FROM event_projects WHERE event_id = ? AND is_primary = 1", (eid,)).fetchone()
    d["primary_project_id"] = prow["project_id"] if prow else None
    d["contact_ids"] = [r["contact_id"] for r in con.execute(
        "SELECT contact_id FROM event_contacts WHERE event_id = ? ORDER BY contact_id", (eid,))]
    d["user_ids"] = [r["user_id"] for r in con.execute(
        "SELECT user_id FROM event_users WHERE event_id = ? ORDER BY user_id", (eid,))]
    return d


def _event_dict(con, event_id: int) -> dict:
    row = con.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()
    return _with_links(con, dict(row))
