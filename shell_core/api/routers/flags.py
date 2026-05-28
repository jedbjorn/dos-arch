"""Open/close/edit/search blockers — substrate task tracking."""
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel, Field
from datetime import date

from api.common.db import get_db, _valid_date, _enum_error
from api.common.auth import _caller_shell

router = APIRouter(tags=["flags"])


FLAG_PRIORITIES = ('High', 'Medium', 'Low')

ACTION_LABELS = {0: "Opened", 1: "Resolved", 2: "Tracking"}

# Includes scheduling fields from the flag_schedule view (effective_start,
# effective_end, schedule_status). The view computes these from
# parent_flag_id + estimated_days + start_date_override (the start_date column).
FLAG_LIST_COLS = """
    f.flag_id, f.display_name, f.description, f.priority,
    f.created_date, f.resolved_date, f.resolved, f.start_date,
    f.parent_flag_id, f.estimated_days,
    f.resolution_notes, f.shell_id,
    fs.effective_start, fs.effective_end, fs.status AS schedule_status
"""

FLAG_BASE_FROM = """
    FROM flags f
    LEFT JOIN flag_schedule fs ON fs.flag_id = f.flag_id
"""

FLAG_DETAIL_SQL = f"""
    SELECT {FLAG_LIST_COLS}
    {FLAG_BASE_FROM}
    WHERE f.flag_id = ?
"""


def _get_flag(con, flag_id: int) -> dict:
    row = con.execute(FLAG_DETAIL_SQL, (flag_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Flag not found")
    return dict(row)


def _check_no_cycle(con, flag_id: int, proposed_parent_id: int) -> None:
    """Walk parent chain upward from proposed_parent_id; raise if flag_id appears.
    Self-parent (flag_id == proposed_parent_id) is rejected directly.
    """
    if flag_id == proposed_parent_id:
        raise HTTPException(422, "A flag cannot be its own parent")
    rows = con.execute("""
        WITH RECURSIVE chain(id) AS (
            SELECT ?
            UNION ALL
            SELECT f.parent_flag_id FROM flags f, chain
             WHERE f.flag_id = chain.id AND f.parent_flag_id IS NOT NULL
        )
        SELECT id FROM chain
    """, (proposed_parent_id,)).fetchall()
    if any(r[0] == flag_id for r in rows):
        raise HTTPException(422, "Cycle detected in parent chain")


def _validate_parent(con, parent_flag_id):
    if parent_flag_id is None:
        return
    if not con.execute(
        "SELECT 1 FROM flags WHERE flag_id = ? AND is_deleted = 0", (parent_flag_id,)
    ).fetchone():
        raise HTTPException(422, f"parent_flag_id {parent_flag_id} not found")


class FlagBody(BaseModel):
    display_name:   str = Field(max_length=250)
    description:    str = ""
    priority:       str = Field(default="Medium", max_length=15)
    status:         int | None = Field(
        default=None, description="0 = Open (default), 1 = Resolved, 2 = Tracking")
    start_date:     str = Field(default="", max_length=25)
    parent_flag_id: int | None = None
    estimated_days: float | None = None
    shell_id:       int | None = None


class StartDateBody(BaseModel):
    start_date: str = Field(default="", max_length=25)


class PriorityBody(BaseModel):
    priority: str = Field(max_length=15)


class NoteBody(BaseModel):
    note: str = ""


class RawNotesBody(BaseModel):
    notes:            str | None = None
    resolution_notes: str | None = None


class ResolveBody(BaseModel):
    status:           int | None = Field(None, description="0 = Open, 1 = Resolved, 2 = Tracking")
    resolved:         int | None = None
    notes:            str = ""
    resolution_notes: str = ""

    @property
    def effective_status(self) -> int:
        v = self.status if self.status is not None else self.resolved
        if v is None:
            raise ValueError("status is required")
        return v

    @property
    def effective_notes(self) -> str:
        return (self.notes or self.resolution_notes).strip()


class UpdateFlagBody(BaseModel):
    display_name:     str         = Field(default="", max_length=250)
    description:      str         = ""
    priority:         str         = Field(default="", max_length=15)
    start_date:       str         = Field(default="", max_length=25)
    parent_flag_id:   int | None  = None
    clear_parent:     bool        = False
    estimated_days:   float | None = None


@router.post("/flags", summary="Create a new flag")
def create_flag(body: FlagBody, request: Request, con = Depends(get_db)):
    if body.priority not in FLAG_PRIORITIES:
        _enum_error("priority", body.priority, FLAG_PRIORITIES)
    _valid_date(body.start_date)
    start_date = body.start_date.strip() or None
    # New flags default to Open (0); Tracking (2) is opt-in via `status`.
    if body.status is not None:
        if body.status not in (0, 1, 2):
            raise HTTPException(422, "status must be 0 (Open), 1 (Resolved), or 2 (Tracking)")
        resolved = body.status
    else:
        resolved = 0
    _validate_parent(con, body.parent_flag_id)
    # Owner: an explicit shell_id in the body wins (the UI sets it from the
    # active shell picker); otherwise default to the calling shell when the
    # Bearer token resolved one. The keyless localhost UI without an
    # explicit shell_id still lands shell_id=NULL — by design, "no owner".
    shell_id = body.shell_id if body.shell_id is not None else _caller_shell(request)
    con.execute("""
        INSERT INTO flags (display_name, priority, description,
                           start_date, parent_flag_id, estimated_days,
                           resolved, created_date, shell_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, date('now'), ?)
    """, (
        body.display_name.strip(),
        body.priority,
        body.description.strip() or None,
        start_date,
        body.parent_flag_id,
        body.estimated_days,
        resolved,
        shell_id,
    ))
    flag_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    con.commit()
    return _get_flag(con, flag_id)


@router.patch("/flags/{flag_id}/priority", summary="Update flag priority")
def update_flag_priority(flag_id: int, body: PriorityBody, con = Depends(get_db)):
    if body.priority not in FLAG_PRIORITIES:
        _enum_error("priority", body.priority, FLAG_PRIORITIES)
    if not con.execute("SELECT 1 FROM flags WHERE flag_id = ? AND is_deleted = 0", (flag_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Flag not found")
    con.execute("UPDATE flags SET priority = ? WHERE flag_id = ?", (body.priority, flag_id))
    con.commit()
    return _get_flag(con, flag_id)


@router.patch("/flags/{flag_id}/start_date", summary="Set or clear flag start_date; resolved transitions automatically")
def update_flag_start_date(flag_id: int, body: StartDateBody, con = Depends(get_db)):
    _valid_date(body.start_date)
    start_date = body.start_date.strip() or None
    flag = con.execute("SELECT resolved, start_date FROM flags WHERE flag_id = ? AND is_deleted = 0", (flag_id,)).fetchone()
    if not flag:
        raise HTTPException(status_code=404, detail="Flag not found")
    if start_date is None:
        new_resolved = 2
    elif flag["resolved"] == 2:
        new_resolved = 0
    else:
        new_resolved = flag["resolved"]
    con.execute(
        "UPDATE flags SET start_date = ?, resolved = ? WHERE flag_id = ?",
        (start_date, new_resolved, flag_id)
    )
    con.commit()
    return _get_flag(con, flag_id)


@router.get("/flags", summary="List flags, optionally scoped to one shell, ordered by status then schedule")
def get_all_flags(shell_id: int | None = None, con = Depends(get_db)):
    """Pass `?shell_id=` to scope the list to one shell. Unscoped (no
    param) keeps the prior behaviour — every flag in the substrate, for
    the admin UI. The OPEN FLAGS prompt pointer and the surface_flags
    skill both rely on this filter — the pointer's per-shell count and
    the skill's per-shell triage must read the same rows."""
    where = ["f.is_deleted = 0"]
    params: list = []
    if shell_id is not None:
        where.append("f.shell_id = ?")
        params.append(shell_id)
    rows = con.execute(f"""
        SELECT {FLAG_LIST_COLS}
        {FLAG_BASE_FROM}
        WHERE {' AND '.join(where)}
        ORDER BY CASE f.resolved WHEN 0 THEN 0 WHEN 2 THEN 1 WHEN 1 THEN 2 END,
                 fs.effective_start ASC NULLS LAST,
                 f.flag_id ASC
    """, params).fetchall()
    return [dict(r) for r in rows]


@router.get("/flags/search", summary="Search flags by name, description, resolution_notes, or numeric flag_id")
def search_flags(q: str = "", con = Depends(get_db)):
    q = (q or "").strip()
    if not q:
        return []
    like = f"%{q}%"
    params = [like, like, like]
    id_clause = ""
    if q.isdigit():
        id_clause = " OR f.flag_id = ?"
        params.append(int(q))
    rows = con.execute(f"""
        SELECT {FLAG_LIST_COLS}
        {FLAG_BASE_FROM}
        WHERE f.is_deleted = 0
          AND (
              f.display_name LIKE ? COLLATE NOCASE
              OR f.description LIKE ? COLLATE NOCASE
              OR f.resolution_notes LIKE ? COLLATE NOCASE
              {id_clause}
          )
        ORDER BY CASE f.resolved WHEN 0 THEN 0 WHEN 2 THEN 1 WHEN 1 THEN 2 END,
                 fs.effective_start ASC NULLS LAST,
                 f.flag_id ASC
    """, params).fetchall()
    return [dict(r) for r in rows]


@router.get("/flags/{flag_id}", summary="Get one flag by id")
def get_flag(flag_id: int, con = Depends(get_db)):
    row = con.execute(FLAG_DETAIL_SQL + " AND f.is_deleted = 0", (flag_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Flag not found")
    return dict(row)


@router.delete("/flags/{flag_id}", summary="Soft-delete a flag (children re-parented to grandparent)")
def delete_flag(flag_id: int, con = Depends(get_db)):
    if not con.execute("SELECT 1 FROM flags WHERE flag_id = ? AND is_deleted = 0", (flag_id,)).fetchone():
        raise HTTPException(404, "Flag not found")
    con.execute("""
        UPDATE flags
           SET parent_flag_id = (SELECT parent_flag_id FROM flags WHERE flag_id = ?)
         WHERE parent_flag_id = ?
    """, (flag_id, flag_id))
    con.execute("UPDATE flags SET is_deleted = 1 WHERE flag_id = ?", (flag_id,))
    con.commit()
    return {"ok": True}


@router.patch("/flags/{flag_id}/note", summary="Append a dated note to flag.resolution_notes")
def add_flag_note(flag_id: int, body: NoteBody, con = Depends(get_db)):
    flag = con.execute("SELECT resolution_notes FROM flags WHERE flag_id = ? AND is_deleted = 0", (flag_id,)).fetchone()
    if not flag:
        raise HTTPException(status_code=404, detail="Flag not found")
    stamp    = date.today().strftime("%b %-d, %Y")
    entry    = f"## Note: {stamp}"
    if body.note.strip():
        entry += f"\n{body.note.strip()}"
    existing = flag["resolution_notes"] or ""
    new_notes = (existing + "\n\n" + entry).strip()
    con.execute("UPDATE flags SET resolution_notes = ? WHERE flag_id = ?", (new_notes, flag_id))
    con.commit()
    return _get_flag(con, flag_id)


@router.put("/flags/{flag_id}/resolution_notes", summary="Replace flag resolution notes")
def put_flag_notes(flag_id: int, body: RawNotesBody, con = Depends(get_db)):
    if not con.execute("SELECT 1 FROM flags WHERE flag_id = ? AND is_deleted = 0", (flag_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Flag not found")
    raw = body.resolution_notes if body.resolution_notes is not None else body.notes
    val = raw.strip() if raw is not None else None
    con.execute("UPDATE flags SET resolution_notes = NULLIF(?, '') WHERE flag_id = ?", (val, flag_id))
    con.commit()
    return _get_flag(con, flag_id)


@router.patch("/flags/{flag_id}/resolve", summary="Resolve, reopen, or set tracking on a flag")
def resolve_flag(flag_id: int, body: ResolveBody, con = Depends(get_db)):
    try:
        status = body.effective_status
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if status not in (0, 1, 2):
        raise HTTPException(status_code=422, detail="status must be 0, 1, or 2")
    flag = con.execute("SELECT resolved, resolution_notes FROM flags WHERE flag_id = ? AND is_deleted = 0", (flag_id,)).fetchone()
    if not flag:
        raise HTTPException(status_code=404, detail="Flag not found")
    # status=0 is "Reopened" only when the flag was actually Resolved before;
    # a first transition (e.g. Tracking → Open) reads as "Opened".
    action        = ACTION_LABELS[status]
    if status == 0 and flag["resolved"] == 1:
        action = "Reopened"
    stamp         = date.today().strftime("%b %-d, %Y")
    entry         = f"## {action}: {stamp}"
    if body.effective_notes:
        entry += f"\n{body.effective_notes}"
    existing      = flag["resolution_notes"] or ""
    new_notes     = (existing + "\n\n" + entry).strip()
    if status == 1:
        con.execute(
            "UPDATE flags SET resolved = ?, resolved_date = date('now'), resolution_notes = ? WHERE flag_id = ?",
            (status, new_notes, flag_id)
        )
    elif status == 2:
        con.execute(
            "UPDATE flags SET resolved = ?, resolved_date = NULL, resolution_notes = ?, start_date = NULL WHERE flag_id = ?",
            (status, new_notes, flag_id)
        )
    else:
        con.execute(
            "UPDATE flags SET resolved = ?, resolved_date = NULL, resolution_notes = ? WHERE flag_id = ?",
            (status, new_notes, flag_id)
        )
    con.commit()
    return _get_flag(con, flag_id)


@router.patch("/flags/{flag_id}", summary="Update one or more flag fields")
def update_flag(flag_id: int, body: UpdateFlagBody, con = Depends(get_db)):
    if body.priority and body.priority not in FLAG_PRIORITIES:
        _enum_error("priority", body.priority, FLAG_PRIORITIES)
    if body.start_date.strip():
        _valid_date(body.start_date)
    flag = con.execute(
        "SELECT resolved, resolution_notes, parent_flag_id FROM flags WHERE flag_id = ? AND is_deleted = 0",
        (flag_id,)
    ).fetchone()
    if not flag:
        raise HTTPException(404, "Flag not found")

    if body.parent_flag_id is not None:
        _validate_parent(con, body.parent_flag_id)
        _check_no_cycle(con, flag_id, body.parent_flag_id)

    con.execute("""
        UPDATE flags SET
            display_name = COALESCE(NULLIF(?, ''), display_name),
            description  = COALESCE(NULLIF(?, ''), description),
            priority     = COALESCE(NULLIF(?, ''), priority)
        WHERE flag_id = ?
    """, (body.display_name.strip(), body.description.strip(), body.priority, flag_id))
    if body.start_date.strip():
        start_date = body.start_date.strip()
        new_resolved = 0 if flag["resolved"] == 2 else flag["resolved"]
        con.execute(
            "UPDATE flags SET start_date = ?, resolved = ? WHERE flag_id = ?",
            (start_date, new_resolved, flag_id)
        )
    if body.parent_flag_id is not None:
        con.execute(
            "UPDATE flags SET parent_flag_id = ? WHERE flag_id = ?",
            (body.parent_flag_id, flag_id)
        )
    elif body.clear_parent:
        con.execute(
            "UPDATE flags SET parent_flag_id = NULL WHERE flag_id = ?",
            (flag_id,)
        )
    if body.estimated_days is not None:
        con.execute(
            "UPDATE flags SET estimated_days = ? WHERE flag_id = ?",
            (body.estimated_days, flag_id)
        )
    con.commit()
    return _get_flag(con, flag_id)
