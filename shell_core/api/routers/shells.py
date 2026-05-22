"""Identity, decisions, archives, chat, messages — the per-shell CRUD surface."""
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel, Field
import re
import uuid
from datetime import date

from api.common.db import get_db
from api.common.auth import _require_shell_creator
from api.services.shell_messaging import _build_message_prompt
from api.services.boot_document import rerender_boot_document, rerender_shell_sessions, session_start_payload

router = APIRouter(tags=["shells"])

# Warn / auto-clear thresholds as a fraction of the session model's context
# window — a fixed token count cannot fit every model. A model with no
# context_window recorded falls back to DEFAULT_CONTEXT_WINDOW.
TOKEN_WARN_FRACTION      = 0.80
TOKEN_AUTOCLEAR_FRACTION = 0.95
DEFAULT_CONTEXT_WINDOW   = 128_000


# ── Shell creation ────────────────────────────────────────────────────────────

class CreateShellBody(BaseModel):
    display_name:      str
    shortname:         str
    role:              str | None = None
    mandate:           str | None = None
    connections:       str | None = None
    partner:           str | None = None
    user_id:           int
    skills:            str = "common"
    api_auth:          int = 0   # 0 = CLI shell (browser-auth); 1 = API shell (broker-routed)


@router.post("/shells", summary="Create a new shell — role / mandate / connections columns (Forge / admin / UI only)")
def create_shell(request: Request, body: CreateShellBody, con = Depends(get_db)):
    _require_shell_creator(request, con)

    short = body.shortname.strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9]{0,7}", short):
        raise HTTPException(422, "shortname must be 1-8 chars, lowercase, starting with a letter")
    if short == "forge":
        raise HTTPException(422, "shortname 'forge' is reserved")
    if con.execute("SELECT 1 FROM shells WHERE shortname=?", (short,)).fetchone():
        raise HTTPException(409, f"shortname '{short}' already exists")
    if not con.execute("SELECT 1 FROM users WHERE user_id=?", (body.user_id,)).fetchone():
        raise HTTPException(404, f"user_id {body.user_id} not found")

    # Identity is columns, not a rendered template: role / mandate frame the
    # shell (catalog Section C), connections is its operating context
    # (Section B). The boot-prompt catalog composes the rest.
    cur = con.execute(
        "INSERT INTO shells (display_name, shortname, partner, role, mandate, "
        "connections, user_id, is_shared, is_admin, api_auth) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, ?)",
        (body.display_name, short, body.partner, body.role, body.mandate,
         body.connections, body.user_id, 1 if body.api_auth else 0),
    )
    new_id = cur.lastrowid

    # Attach skills — `common` expands to every common=1 skill; named extras
    # may be mixed in (matches db_init._attach_skills).
    skill_ids: set[int] = set()
    for tok in (s.strip() for s in body.skills.split(",") if s.strip()):
        if tok == "common":
            skill_ids.update(r[0] for r in con.execute(
                "SELECT skill_id FROM skills WHERE common=1 AND is_deleted=0"))
        else:
            r = con.execute(
                "SELECT skill_id FROM skills WHERE name=? AND is_deleted=0", (tok,)
            ).fetchone()
            if r:
                skill_ids.add(r[0])
    con.executemany(
        "INSERT OR IGNORE INTO shell_skills (shell_id, skill_id) VALUES (?, ?)",
        [(new_id, sid) for sid in skill_ids],
    )
    # Tools need no per-shell grant — general tools are universal, and a
    # skill-bound tool comes with its skill (attached above).
    con.commit()
    return {"shell_id": new_id, "shortname": short, "skills_attached": len(skill_ids)}


# ── Shell directory / activation ──────────────────────────────────────────────

@router.get("/shells/mine", summary="List shells assigned to the authenticated user")
def get_my_shells(request: Request, con = Depends(get_db)):
    user_id = getattr(request.state, "user_id", 1)
    rows = con.execute(
        "SELECT shell_id, display_name, shortname, browser_chat FROM shells WHERE user_id=? AND shell_id > 0 ORDER BY shell_id",
        (user_id,)
    ).fetchall()
    return [dict(r) for r in rows]


@router.patch("/shells/{shell_id}/activate", summary="Activate this shell as the user's browser-chat target")
def activate_shell(shell_id: int, request: Request, con = Depends(get_db)):
    user_id = getattr(request.state, "user_id", 1)
    con.execute("BEGIN IMMEDIATE")
    try:
        if not con.execute(
            "SELECT 1 FROM shells WHERE shell_id=? AND user_id=?",
            (shell_id, user_id),
        ).fetchone():
            con.rollback()
            raise HTTPException(404, "Shell not found or not assigned to you")
        con.execute("UPDATE shells SET browser_chat=0 WHERE user_id=?", (user_id,))
        cur = con.execute(
            "UPDATE shells SET browser_chat=1 WHERE shell_id=? AND user_id=?",
            (shell_id, user_id),
        )
        if cur.rowcount != 1:
            con.rollback()
            raise HTTPException(404, "Shell not found or not assigned to you")
        con.commit()
    except HTTPException:
        raise
    except Exception:
        con.rollback()
        raise
    return {"shell_id": shell_id, "browser_chat": True}


# ── Shell record ──────────────────────────────────────────────────────────────

@router.get("/shells/{shell_id}", summary="Get one shell record")
def get_shell(shell_id: int, con = Depends(get_db)):
    row = con.execute("""
        SELECT shell_id, display_name, shortname, partner, role, mandate,
               current_state, connections, api_endpoints,
               active_archive_id, api_auth
        FROM shells WHERE shell_id = ?
    """, (shell_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Shell not found")
    return dict(row)


@router.get("/shells/{shell_id}/sessions/{session_id}/session-start", summary="Boot document (materialized) + live dynamic tail — the dispatcher's per-turn read")
def get_shell_session_start(shell_id: int, session_id: str, con = Depends(get_db)):
    if not con.execute(
        "SELECT 1 FROM chat_sessions WHERE chat_session_id=? AND shell_id=?",
        (session_id, shell_id),
    ).fetchone():
        raise HTTPException(404, "Session not found")
    payload = session_start_payload(con, session_id)
    con.commit()  # persists a lazy first-time materialization, if one happened
    return payload


class UpdateShellBody(BaseModel):
    display_name:      str | None = None
    shortname:         str | None = None
    partner:           str | None = None
    role:              str | None = None
    mandate:           str | None = None
    current_state:     str | None = None
    connections:       str | None = None
    api_endpoints:     str | None = None
    active_archive_id: int | None = None
    api_auth:          int | None = None


@router.patch("/shells/{shell_id}", summary="Update one or more shell fields")
def update_shell(shell_id: int, body: UpdateShellBody, con = Depends(get_db)):
    if not con.execute("SELECT 1 FROM shells WHERE shell_id=?", (shell_id,)).fetchone():
        raise HTTPException(404, "Shell not found")
    fields, args = [], []
    if body.display_name is not None:
        name = body.display_name.strip()
        if not name:
            raise HTTPException(422, "display_name cannot be empty")
        fields.append("display_name = ?"); args.append(name)
    if body.shortname is not None:
        short = body.shortname.strip().lower()
        if not re.fullmatch(r"[a-z][a-z0-9]{0,7}", short):
            raise HTTPException(422, "shortname must be 1-8 chars, lowercase, starting with a letter")
        if short == "forge":
            raise HTTPException(422, "shortname 'forge' is reserved")
        if con.execute("SELECT 1 FROM shells WHERE shortname=? AND shell_id<>?", (short, shell_id)).fetchone():
            raise HTTPException(409, f"shortname '{short}' already exists")
        fields.append("shortname = ?"); args.append(short)
    if body.partner is not None:
        fields.append("partner = ?"); args.append(body.partner.strip() or None)
    if body.role is not None:
        fields.append("role = ?"); args.append(body.role.strip() or None)
    if body.mandate is not None:
        fields.append("mandate = ?"); args.append(body.mandate.strip() or None)
    if body.current_state is not None:
        # Rolling status — length is a rendered soft ~target, not enforced
        # here (soft caps, spec §04 / migration 020).
        state = body.current_state.strip() or None
        fields.append("current_state = ?"); args.append(state)
    if body.connections is not None:
        fields.append("connections = ?"); args.append(body.connections.strip() or None)
    if body.api_endpoints is not None:
        fields.append("api_endpoints = ?"); args.append(body.api_endpoints.strip() or None)
    if body.active_archive_id is not None:
        fields.append("active_archive_id = ?"); args.append(body.active_archive_id)
    if body.api_auth is not None:
        # 0 = CLI shell (browser-auth) · 1 = API shell (broker-routed Anthropic).
        # Takes effect on the shell's next `make launch` — run.py reads api_auth
        # at boot to decide whether to inject the broker's ANTHROPIC_BASE_URL.
        fields.append("api_auth = ?"); args.append(1 if body.api_auth else 0)
    if fields:
        args.append(shell_id)
        con.execute(f"UPDATE shells SET {', '.join(fields)} WHERE shell_id = ?", args)
        # An identity-surface change touches every live session's boot
        # document — re-materialize them all.
        if any(getattr(body, f) is not None for f in
               ("display_name", "shortname", "partner", "role", "mandate", "current_state")):
            rerender_shell_sessions(con, shell_id)
        con.commit()
    # Same column set as GET /shells/{id} — a PATCH round-trip is symmetric.
    row = con.execute("""
        SELECT shell_id, display_name, shortname, partner, role, mandate,
               current_state, connections, api_endpoints,
               active_archive_id, api_auth
        FROM shells WHERE shell_id = ?
    """, (shell_id,)).fetchone()
    return dict(row)


# ── Shell identity entries (seed + L&S) ───────────────────────────────────────

class CreateIdentityEntryBody(BaseModel):
    kind:       str
    body:       str
    entry_date: str | None = None
    source_tag: str | None = None


@router.post("/shells/{shell_id}/identity-entries", summary="Create a seed or L&S entry (count cap enforced via trigger)")
def create_identity_entry(shell_id: int, body: CreateIdentityEntryBody, con = Depends(get_db)):
    if not con.execute("SELECT 1 FROM shells WHERE shell_id=?", (shell_id,)).fetchone():
        raise HTTPException(404, "Shell not found")
    if body.kind not in ("seed", "lns"):
        raise HTTPException(422, "kind must be 'seed' or 'lns'")
    entry_body = body.body.strip()
    if not entry_body:
        raise HTTPException(422, "body is required")
    # Body length is a rendered soft ~target as of migration 020 — not
    # enforced here. The count caps (10 seed / 20 L&S) stay trigger-enforced;
    # the INSERT below catches that ABORT and surfaces it as a 409.
    try:
        cur = con.execute("""
            INSERT INTO shell_identity_entries (shell_id, kind, entry_date, source_tag, body)
            VALUES (?, ?, ?, ?, ?)
        """, (
            shell_id,
            body.kind,
            (body.entry_date or "").strip() or str(date.today()),
            (body.source_tag or "").strip() or None,
            entry_body,
        ))
        rerender_shell_sessions(con, shell_id)
        con.commit()
    except Exception as e:
        con.rollback()
        msg = str(e)
        if "cap" in msg.lower():
            raise HTTPException(409, msg)
        raise
    row = con.execute(
        "SELECT entry_id, shell_id, kind, entry_date, source_tag, body, created_at, retired_at FROM shell_identity_entries WHERE entry_id = ?",
        (cur.lastrowid,)
    ).fetchone()
    return dict(row)


class UpdateIdentityEntryBody(BaseModel):
    retire: bool = False


@router.patch("/shells/{shell_id}/identity-entries/{entry_id}", summary="Retire an identity entry (Law 3 — preserved row, no edit)")
def update_identity_entry(shell_id: int, entry_id: int, body: UpdateIdentityEntryBody, con = Depends(get_db)):
    row = con.execute(
        "SELECT * FROM shell_identity_entries WHERE shell_id = ? AND entry_id = ?",
        (shell_id, entry_id)
    ).fetchone()
    if not row:
        raise HTTPException(404, "Entry not found")
    if not body.retire:
        raise HTTPException(422, "only retirement is supported (Law 3 — preserved row, no edit)")
    if row["retired_at"]:
        raise HTTPException(409, "entry already retired")
    con.execute(
        "UPDATE shell_identity_entries SET retired_at = datetime('now') WHERE entry_id = ?",
        (entry_id,)
    )
    rerender_shell_sessions(con, shell_id)
    con.commit()
    row = con.execute(
        "SELECT entry_id, shell_id, kind, entry_date, source_tag, body, created_at, retired_at FROM shell_identity_entries WHERE entry_id = ?",
        (entry_id,)
    ).fetchone()
    return dict(row)


@router.get("/shells/{shell_id}/identity-entries", summary="List a shell's seed + L&S entries")
def list_identity_entries(shell_id: int, kind: str = "", include_retired: bool = False,
                          con = Depends(get_db)):
    """Inspect own seed/L&S mid-session — needed to find entry_ids before a
    retire PATCH. Active entries only by default; pass include_retired=true
    for the full curated history."""
    if not con.execute("SELECT 1 FROM shells WHERE shell_id=?", (shell_id,)).fetchone():
        raise HTTPException(404, "Shell not found")
    if kind and kind not in ("seed", "lns"):
        raise HTTPException(422, "kind must be 'seed' or 'lns'")
    sql = ("SELECT entry_id, shell_id, kind, entry_date, source_tag, body, "
           "created_at, retired_at FROM shell_identity_entries "
           "WHERE shell_id = ? AND is_deleted = 0")
    args: list = [shell_id]
    if kind:
        sql += " AND kind = ?"; args.append(kind)
    if not include_retired:
        sql += " AND retired_at IS NULL"
    sql += " ORDER BY kind, entry_date, entry_id"
    rows = con.execute(sql, args).fetchall()
    return {"shell_id": shell_id, "count": len(rows), "entries": [dict(r) for r in rows]}


# ── Shell decisions (per-shell decision log) ─────────────────────────────────

class CreateDecisionBody(BaseModel):
    decision_date:      str
    priority:           str = "M"
    decision:           str
    rationale:          str | None = None
    parent_decision_id: int | None = None


@router.post("/shells/{shell_id}/decisions", summary="Record a major (M) decision")
def create_decision(shell_id: int, body: CreateDecisionBody, con = Depends(get_db)):
    if not con.execute("SELECT 1 FROM shells WHERE shell_id=?", (shell_id,)).fetchone():
        raise HTTPException(404, "Shell not found")
    if body.priority not in ("M", "m"):
        raise HTTPException(422, "priority must be 'M' or 'm'")
    if not body.decision.strip():
        raise HTTPException(422, "decision is required")
    cur = con.execute("""
        INSERT INTO shell_decisions
            (shell_id, decision_date, priority, decision, rationale, parent_decision_id)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        shell_id,
        body.decision_date.strip(),
        body.priority,
        body.decision.strip(),
        (body.rationale or "").strip() or None,
        body.parent_decision_id,
    ))
    con.commit()
    row = con.execute(
        "SELECT * FROM shell_decisions WHERE decision_id = ?",
        (cur.lastrowid,)
    ).fetchone()
    return dict(row)


@router.get("/shells/{shell_id}/decisions", summary="List + filter decisions for a shell")
def list_decisions(shell_id: int, q: str = "", priority: str = "",
                   date_from: str = "", date_to: str = "",
                   include_deleted: bool = False, con = Depends(get_db)):
    if not con.execute("SELECT 1 FROM shells WHERE shell_id=?", (shell_id,)).fetchone():
        raise HTTPException(404, "Shell not found")
    sql = "SELECT * FROM shell_decisions WHERE shell_id = ?"
    args: list = [shell_id]
    if not include_deleted:
        sql += " AND is_deleted = 0"
    if priority:
        sql += " AND priority = ?"
        args.append(priority.strip())
    if date_from:
        sql += " AND decision_date >= ?"
        args.append(date_from)
    if date_to:
        sql += " AND decision_date <= ?"
        args.append(date_to)
    if q:
        sql += " AND (decision LIKE ? OR rationale LIKE ?)"
        args.extend([f"%{q}%", f"%{q}%"])
    sql += " ORDER BY decision_date DESC, decision_id DESC"
    rows = con.execute(sql, args).fetchall()
    return {"shell_id": shell_id, "count": len(rows), "decisions": [dict(r) for r in rows]}


class UpdateDecisionBody(BaseModel):
    decision_date:      str | None = None
    priority:           str | None = None
    decision:           str | None = None
    rationale:          str | None = None
    parent_decision_id: int | None = None
    is_deleted:         int | None = None


@router.patch("/shells/{shell_id}/decisions/{decision_id}", summary="Update or soft-delete a decision")
def update_decision(shell_id: int, decision_id: int, body: UpdateDecisionBody, con = Depends(get_db)):
    row = con.execute(
        "SELECT * FROM shell_decisions WHERE shell_id = ? AND decision_id = ?",
        (shell_id, decision_id)
    ).fetchone()
    if not row:
        raise HTTPException(404, "Decision not found")
    fields, args = [], []
    if body.decision_date is not None:
        fields.append("decision_date = ?"); args.append(body.decision_date.strip())
    if body.priority is not None:
        if body.priority not in ("M", "m"):
            raise HTTPException(422, "priority must be 'M' or 'm'")
        fields.append("priority = ?"); args.append(body.priority)
    if body.decision is not None:
        if not body.decision.strip():
            raise HTTPException(422, "decision cannot be empty")
        fields.append("decision = ?"); args.append(body.decision.strip())
    if body.rationale is not None:
        fields.append("rationale = ?"); args.append(body.rationale.strip() or None)
    if body.parent_decision_id is not None:
        fields.append("parent_decision_id = ?"); args.append(body.parent_decision_id)
    if body.is_deleted is not None:
        fields.append("is_deleted = ?"); args.append(1 if body.is_deleted else 0)
    if fields:
        args.extend([shell_id, decision_id])
        con.execute(f"UPDATE shell_decisions SET {', '.join(fields)} WHERE shell_id = ? AND decision_id = ?", args)
        con.commit()
    row = con.execute(
        "SELECT * FROM shell_decisions WHERE decision_id = ?",
        (decision_id,)
    ).fetchone()
    return dict(row)


# ── Memory lookup ────────────────────────────────────────────────────────────


@router.get("/shells/{shell_id}/archives/{session_id}", summary="Get one session archive by session_id")
def get_archive_by_session(shell_id: int, session_id: str, con = Depends(get_db)):
    row = con.execute(
        "SELECT * FROM shell_memory_archives WHERE shell_id = ? AND session_id = ?",
        (shell_id, session_id.strip()),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Archive not found")
    return dict(row)


@router.get("/shells/{shell_id}/archives", summary="Search session archives by date range or narrative content")
def search_archives(shell_id: int, date_from: str = "", date_to: str = "", q: str = "", fields: str = "session_id,date", con = Depends(get_db)):
    allowed = {"archive_id", "session_id", "date", "full_narrative"}
    selected = [f.strip() for f in fields.split(",") if f.strip() in allowed]
    if not selected:
        selected = ["session_id", "date"]
    sql = f"SELECT {', '.join(selected)} FROM shell_memory_archives WHERE shell_id = ?"
    args: list = [shell_id]
    if date_from:
        sql += " AND date >= ?"
        args.append(date_from)
    if date_to:
        sql += " AND date <= ?"
        args.append(date_to)
    if q:
        sql += " AND full_narrative LIKE ?"
        args.append(f"%{q}%")
    sql += " ORDER BY date, session_id"
    rows = con.execute(sql, args).fetchall()
    return {"shell_id": shell_id, "count": len(rows), "archives": [dict(r) for r in rows]}


class IgnoreMessagesBody(BaseModel):
    ignore: bool


@router.patch("/shells/{shell_id}/ignore-messages", summary="Toggle whether this shell ignores incoming messages")
def set_ignore_messages(shell_id: int, body: IgnoreMessagesBody, con = Depends(get_db)):
    if not con.execute("SELECT 1 FROM shells WHERE shell_id=?", (shell_id,)).fetchone():
        raise HTTPException(404, "Shell not found")
    if body.ignore:
        con.execute(
            "UPDATE shells SET ignore_messages=1, ignore_messages_since=datetime('now') WHERE shell_id=?",
            (shell_id,)
        )
    else:
        con.execute(
            "UPDATE shells SET ignore_messages=0, ignore_messages_since=NULL WHERE shell_id=?",
            (shell_id,)
        )
    con.commit()
    return {"shell_id": shell_id, "ignore_messages": body.ignore}


# ── Shell messages ────────────────────────────────────────────────────────────

@router.get("/shell-messages", summary="List shell messages by recipient (optionally filtered by read state)")
def get_shell_messages(recipient_id: int, read: int | None = None, con = Depends(get_db)):
    where, params = ["recipient_id = ?"], [recipient_id]
    if read is not None:
        where.append("read = ?"); params.append(read)
    rows = con.execute(f"""
        SELECT * FROM shell_messages
        WHERE {' AND '.join(where)}
        ORDER BY sent_at DESC
    """, params).fetchall()
    return [dict(r) for r in rows]


class CreateMessageBody(BaseModel):
    sender_id:           int
    recipient_id:        int
    subject:             str = Field(default="", max_length=250)
    body:                str
    reply_to_message_id: int | None = None
    auto_prompt:         bool = True
    session_context:     str = ""
    user_issue:          bool = False


@router.post("/shell-messages", summary="Send a message between shells (auto-creates a recipient prompt)")
def create_shell_message(body: CreateMessageBody, con = Depends(get_db)):
    if not body.body.strip():
        raise HTTPException(422, "body is required")
    con.execute("""
        INSERT INTO shell_messages (sender_id, recipient_id, subject, body, reply_to_message_id, user_issue)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (body.sender_id, body.recipient_id,
          body.subject.strip() or None,
          body.body.strip(),
          body.reply_to_message_id,
          1 if body.user_issue else 0))
    message_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    con.commit()

    if body.auto_prompt:
        sender = con.execute(
            "SELECT display_name, current_state FROM shells WHERE shell_id = ?", (body.sender_id,)
        ).fetchone()
        sender_name = sender["display_name"] if sender else f"shell_{body.sender_id}"
        context = body.session_context.strip() or (sender["current_state"] or "" if sender else "")
        prompt_text = _build_message_prompt(
            message_id, body.sender_id, sender_name, body.recipient_id,
            body.subject.strip(), body.body.strip(), context
        )
        subject_label = body.subject.strip() or "incoming message"
        con.execute("""
            INSERT INTO shell_prompt_automations (display_name, text, date, successful, needs_attention, shell_id)
            VALUES (?, ?, date('now'), 0, 0, ?)
        """, (f"Message: {subject_label}", prompt_text, body.recipient_id))
        con.commit()

    row = con.execute("SELECT * FROM shell_messages WHERE message_id = ?", (message_id,)).fetchone()
    return dict(row)


@router.patch("/shell-messages/{message_id}", summary="Mark a shell message as read")
def update_shell_message(message_id: int, con = Depends(get_db)):
    msg = con.execute("SELECT recipient_id FROM shell_messages WHERE message_id = ?", (message_id,)).fetchone()
    if not msg:
        raise HTTPException(404, "Message not found")
    con.execute("UPDATE shell_messages SET read = 1 WHERE message_id = ?", (message_id,))
    con.commit()
    row = con.execute("SELECT * FROM shell_messages WHERE message_id = ?", (message_id,)).fetchone()
    return dict(row)


# ── Shell memory archives ─────────────────────────────────────────────────────

class CreateArchiveBody(BaseModel):
    shell_id:            int
    session_id:          str = ""
    date:                str
    full_narrative:      str = ""


@router.post("/shell-memory-archives", summary="Open a new session archive row for a shell")
def create_shell_memory_archive(body: CreateArchiveBody, con = Depends(get_db)):
    try:
        con.execute("""
            INSERT INTO shell_memory_archives (shell_id, session_id, date, full_narrative)
            VALUES (?, ?, ?, ?)
        """, (
            body.shell_id,
            body.session_id.strip(),
            body.date.strip() or str(date.today()),
            body.full_narrative.strip() or None,
        ))
        archive_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
        con.commit()
        row = con.execute("SELECT * FROM shell_memory_archives WHERE archive_id = ?", (archive_id,)).fetchone()
        return dict(row)
    except Exception as e:
        con.rollback()
        print(f"[ERROR] create_shell_memory_archive: {e}", flush=True)
        raise HTTPException(500, "Internal server error")


@router.get("/shell-memory-archives/{archive_id}", summary="Get one session archive by archive_id")
def get_shell_memory_archive(archive_id: int, con = Depends(get_db)):
    """Direct read by archive_id — the clean mid-session path to the current
    archive, whose id is in the shell's `## ACTIVE SESSION` block."""
    row = con.execute("SELECT * FROM shell_memory_archives WHERE archive_id = ?", (archive_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Archive not found")
    return dict(row)


class UpdateArchiveBody(BaseModel):
    narrative_entry: str


@router.patch("/shell-memory-archives/{archive_id}", summary="Append an entry to an archive's full_narrative")
def update_shell_memory_archive(archive_id: int, body: UpdateArchiveBody, con = Depends(get_db)):
    row = con.execute("SELECT * FROM shell_memory_archives WHERE archive_id = ?", (archive_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Archive not found")
    entry = body.narrative_entry.strip()
    if not entry:
        raise HTTPException(422, "narrative_entry is required")
    new_narrative = (row["full_narrative"] or "") + "\n" + entry
    con.execute(
        "UPDATE shell_memory_archives SET full_narrative = ? WHERE archive_id = ?",
        (new_narrative.strip(), archive_id)
    )
    con.commit()
    row = con.execute("SELECT * FROM shell_memory_archives WHERE archive_id = ?", (archive_id,)).fetchone()
    return dict(row)


# ── Chat + sessions ───────────────────────────────────────────────────────────

@router.get("/shells/{shell_id}/chat", summary="List chat messages for a shell (or just unread inbound)")
def get_shell_chat(shell_id: int, pending: bool = False, con = Depends(get_db)):
    if not con.execute("SELECT 1 FROM shells WHERE shell_id=?", (shell_id,)).fetchone():
        raise HTTPException(404, "Shell not found")
    if pending:
        rows = con.execute(
            """SELECT cm.message_id, cm.direction, cm.user_id, cm.body, cm.sent_at, cm.read_by_shell, cm.tokens
                 FROM chat_messages cm
                 JOIN users u ON u.user_id = cm.user_id AND u.is_active = 1
                WHERE cm.shell_id=? AND cm.direction='inbound'
                  AND cm.read_by_shell=0 AND cm.is_deleted=0
                ORDER BY cm.sent_at ASC""",
            (shell_id,)
        ).fetchall()
    else:
        rows = con.execute(
            """SELECT message_id, direction, user_id, body, sent_at, read_by_shell, tokens, chat_session_id
                 FROM chat_messages WHERE shell_id=? AND is_deleted=0
                ORDER BY sent_at ASC""",
            (shell_id,)
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/shells/{shell_id}/chat/session", summary="Get the user's active chat session for this shell")
def get_chat_session(shell_id: int, request: Request, con = Depends(get_db)):
    user_id = getattr(request.state, 'user_id', 1)
    row = con.execute(
        "SELECT chat_session_id, started_at, last_active, is_active, total_tokens, model_id FROM chat_sessions WHERE shell_id=? AND user_id=? AND is_active=1 ORDER BY last_active DESC LIMIT 1",
        (shell_id, user_id)
    ).fetchone()
    return dict(row) if row else None


def _check_model(con, model_id):
    """Reject an unknown or inactive model_id. None passes — the dispatcher
    falls back to its default for a session with no model pinned."""
    if model_id is not None and not con.execute(
        "SELECT 1 FROM models WHERE model_id=? AND status='active'", (model_id,)
    ).fetchone():
        raise HTTPException(422, "unknown or inactive model_id")


def _model_switch_note(con, old_model_id, new_model_id) -> str:
    """The marker-message body for a model switch — `model: <old> → <new>`,
    using each model's display_name (falling back to its name)."""
    def label(mid):
        if mid is None:
            return "none"
        r = con.execute(
            "SELECT display_name, name FROM models WHERE model_id=?", (mid,)
        ).fetchone()
        return (r["display_name"] or r["name"]) if r else f"model {mid}"
    return f"model: {label(old_model_id)} → {label(new_model_id)}"


@router.post("/shells/{shell_id}/chat/session", summary="Create a new chat session for this shell + user")
def create_chat_session(shell_id: int, request: Request, body: dict | None = None, con = Depends(get_db)):
    user_id = getattr(request.state, 'user_id', 1)
    session_id = str(uuid.uuid4())
    if not con.execute("SELECT 1 FROM shells WHERE shell_id=?", (shell_id,)).fetchone():
        raise HTTPException(404, "Shell not found")
    model_id = (body or {}).get("model_id")
    _check_model(con, model_id)
    con.execute("UPDATE chat_sessions SET is_active=0 WHERE shell_id=? AND user_id=?", (shell_id, user_id))
    con.execute(
        "INSERT INTO chat_sessions (chat_session_id, shell_id, user_id, model_id) VALUES (?,?,?,?)",
        (session_id, shell_id, user_id, model_id),
    )
    # Render the new session's boot document — its model sets the tool
    # dialect for the Tools / Output Shape sections.
    rerender_boot_document(con, session_id)
    con.commit()
    row = dict(con.execute(
        "SELECT chat_session_id, started_at, last_active, is_active, model_id FROM chat_sessions WHERE chat_session_id=?",
        (session_id,)
    ).fetchone())
    return row


@router.get("/shells/{shell_id}/sessions/active", summary="Get the active chat session with token usage")
def get_active_session(shell_id: int, user_id: int, con = Depends(get_db)):
    row = con.execute(
        "SELECT chat_session_id, total_tokens, token_warning_sent FROM chat_sessions "
        "WHERE shell_id=? AND user_id=? AND is_active=1 AND total_tokens > 0 "
        "ORDER BY last_active DESC LIMIT 1",
        (shell_id, user_id)
    ).fetchone()
    if not row:
        return None
    return {"session_id": row[0], "total_tokens": row[1], "token_warning_sent": bool(row[2])}


@router.patch("/shells/{shell_id}/sessions/{session_id}", summary="Update session token counters, model, and warning flags")
def update_session(shell_id: int, session_id: str, body: dict, con = Depends(get_db)):
    existing = con.execute(
        "SELECT model_id FROM chat_sessions WHERE chat_session_id=? AND shell_id=?",
        (session_id, shell_id),
    ).fetchone()
    if not existing:
        raise HTTPException(404, "Session not found")
    fields, params = [], []
    if "total_tokens" in body:
        fields.append("total_tokens=?"); params.append(body["total_tokens"])
    if "token_warning_sent" in body:
        fields.append("token_warning_sent=?"); params.append(1 if body["token_warning_sent"] else 0)
    model_changed = False
    if "model_id" in body:
        _check_model(con, body["model_id"])
        fields.append("model_id=?"); params.append(body["model_id"])
        model_changed = body["model_id"] != existing["model_id"]
    if fields:
        params += [session_id, shell_id]
        con.execute(f"UPDATE chat_sessions SET last_active=CURRENT_TIMESTAMP,{','.join(fields)} WHERE chat_session_id=? AND shell_id=?", params)
        # A real model switch changes this session's tool dialect — re-materialize
        # its boot document in place, and post a marker message so the chat keeps
        # a visible record of the switch (substrate decision #123). A PATCH with
        # no model_id, or one setting it to its current value, does neither.
        if model_changed:
            rerender_boot_document(con, session_id)
            con.execute(
                "INSERT INTO chat_messages (shell_id, direction, body, chat_session_id) "
                "VALUES (?, 'outbound', ?, ?)",
                (shell_id,
                 _model_switch_note(con, existing["model_id"], body["model_id"]),
                 session_id),
            )
        con.commit()
        # Evicting the previous local model is the dispatcher's job — see
        # services/local_model_reaper.py. The API runs in a container that
        # can't reach host Ollama, so this side stops at the model_id write.
    row = dict(con.execute("SELECT chat_session_id, total_tokens, token_warning_sent, is_active, model_id FROM chat_sessions WHERE chat_session_id=?", (session_id,)).fetchone())
    return row


@router.post("/shells/{shell_id}/sessions/{session_id}/clear", summary="Clear (deactivate) a chat session")
def clear_session(shell_id: int, session_id: str, con = Depends(get_db)):
    if not con.execute("SELECT 1 FROM chat_sessions WHERE chat_session_id=? AND shell_id=?", (session_id, shell_id)).fetchone():
        raise HTTPException(404, "Session not found")
    con.execute("UPDATE chat_sessions SET is_active=0 WHERE chat_session_id=?", (session_id,))
    con.execute("UPDATE chat_messages SET is_deleted=1 WHERE chat_session_id=?", (session_id,))
    con.commit()
    return {"cleared": True, "session_id": session_id}


@router.post("/shells/{shell_id}/chat", summary="Post a user-chat message to a shell (inbound)")
def post_shell_chat(shell_id: int, body: dict, request: Request, con = Depends(get_db)):
    user_id = getattr(request.state, 'user_id', 1)
    if not con.execute("SELECT 1 FROM shells WHERE shell_id=?", (shell_id,)).fetchone():
        raise HTTPException(404, "Shell not found")
    text = (body.get("body") or "").strip()
    if not text:
        raise HTTPException(400, "body required")
    chat_session_id = body.get("chat_session_id") or None
    if chat_session_id:
        con.execute("UPDATE chat_sessions SET last_active=CURRENT_TIMESTAMP WHERE chat_session_id=?", (chat_session_id,))
    cur = con.execute(
        "INSERT INTO chat_messages (shell_id, direction, user_id, body, chat_session_id) VALUES (?,?,?,?,?)",
        (shell_id, "inbound", user_id, text, chat_session_id)
    )
    con.commit()
    row = dict(con.execute(
        "SELECT message_id, direction, user_id, body, sent_at, read_by_shell FROM chat_messages WHERE message_id=?",
        (cur.lastrowid,)
    ).fetchone())
    return row


@router.post("/shells/{shell_id}/chat/reply", summary="Post a shell reply with token accounting + auto-clear")
def post_shell_chat_reply(shell_id: int, body: dict, con = Depends(get_db)):
    text = (body.get("body") or "").strip()
    if not text:
        raise HTTPException(400, "body required")

    source_id  = body.get("source_message_id")
    session_id = body.get("session_id")
    user_id    = body.get("user_id")
    call_tokens = int(body.get("tokens") or 0)
    cache_hit   = body.get("cache_hit_tokens")
    cache_miss  = body.get("cache_miss_tokens")
    is_new     = bool(body.get("is_new_session", False))

    if source_id:
        con.execute("UPDATE chat_messages SET read_by_shell=1 WHERE message_id=? AND shell_id=?", (source_id, shell_id))

    cleared        = False
    new_session_id = None
    if session_id and user_id:
        if is_new:
            con.execute("UPDATE chat_sessions SET is_active=0 WHERE shell_id=? AND user_id=? AND total_tokens=0", (shell_id, user_id))
            con.execute(
                "INSERT OR IGNORE INTO chat_sessions (chat_session_id, shell_id, user_id, total_tokens) VALUES (?,?,?,?)",
                (session_id, shell_id, user_id, call_tokens)
            )
        else:
            # total_tokens is the live context size — this turn's count, not a
            # running sum (each turn's count already includes the whole history).
            con.execute(
                "UPDATE chat_sessions SET last_active=CURRENT_TIMESTAMP, total_tokens=? WHERE chat_session_id=?",
                (call_tokens, session_id)
            )

    cur = con.execute(
        "INSERT INTO chat_messages "
        "(shell_id, direction, body, chat_session_id, tokens, "
        "cache_hit_tokens, cache_miss_tokens) VALUES (?,?,?,?,?,?,?)",
        (shell_id, "outbound", text, session_id, call_tokens, cache_hit, cache_miss)
    )
    reply_id = cur.lastrowid

    # Warn / auto-clear thresholds scale with the session model's context
    # window; call_tokens is this turn's context size (see total_tokens above).
    window = DEFAULT_CONTEXT_WINDOW
    if session_id:
        wrow = con.execute(
            "SELECT m.context_window FROM chat_sessions cs "
            "LEFT JOIN models m ON m.model_id = cs.model_id "
            "WHERE cs.chat_session_id=?", (session_id,)
        ).fetchone()
        if wrow and wrow[0]:
            window = wrow[0]
    warn_at  = window * TOKEN_WARN_FRACTION
    clear_at = window * TOKEN_AUTOCLEAR_FRACTION

    if session_id and user_id and call_tokens >= warn_at:
        warned = con.execute("SELECT token_warning_sent FROM chat_sessions WHERE chat_session_id=?", (session_id,)).fetchone()
        if warned and not warned[0]:
            con.execute(
                "INSERT INTO chat_messages (shell_id, direction, body, chat_session_id) VALUES (?,?,?,?)",
                (shell_id, "outbound",
                 f"⚠️ This conversation is nearing the context limit — it will "
                 f"auto-clear at ~{int(clear_at) // 1000}k tokens. Use +chat to "
                 "start fresh before then if needed.",
                 session_id)
            )
            con.execute("UPDATE chat_sessions SET token_warning_sent=1 WHERE chat_session_id=?", (session_id,))

    if session_id and user_id and call_tokens >= clear_at:
        # Over the limit — retire this session and open a fresh one so the
        # conversation has a live session to continue in; the next message
        # would otherwise land in a deactivated session. The replacement keeps
        # the retired session's model; its boot document renders now.
        old = con.execute(
            "SELECT model_id FROM chat_sessions WHERE chat_session_id=?", (session_id,)
        ).fetchone()
        con.execute("UPDATE chat_sessions SET is_active=0 WHERE chat_session_id=?", (session_id,))
        con.execute("UPDATE chat_messages SET is_deleted=1 WHERE chat_session_id=?", (session_id,))
        new_session_id = str(uuid.uuid4())
        con.execute(
            "INSERT INTO chat_sessions (chat_session_id, shell_id, user_id, model_id) "
            "VALUES (?,?,?,?)",
            (new_session_id, shell_id, user_id, old["model_id"] if old else None),
        )
        rerender_boot_document(con, new_session_id)
        con.execute(
            "INSERT INTO chat_messages (shell_id, direction, body, chat_session_id) "
            "VALUES (?,?,?,?)",
            (shell_id, "outbound",
             f"Session cleared — context limit reached (~{int(clear_at) // 1000}k "
             "tokens). Starting fresh.",
             new_session_id),
        )
        cleared = True

    con.commit()
    row = dict(con.execute(
        "SELECT message_id, direction, user_id, body, sent_at, read_by_shell FROM chat_messages WHERE message_id=?",
        (reply_id,)
    ).fetchone())
    return {**row, "session_total_tokens": call_tokens, "cleared": cleared,
            "new_session_id": new_session_id}


@router.delete("/shells/{shell_id}/chat", summary="Soft-delete chat history for a shell (optionally before a message_id)")
def delete_shell_chat(shell_id: int, body: dict, request: Request, con = Depends(get_db)):
    user_id = getattr(request.state, 'user_id', 1)
    before_id = body.get("before_id")
    if before_id:
        con.execute(
            "UPDATE chat_messages SET is_deleted=1 WHERE shell_id=? AND message_id<=?",
            (shell_id, before_id)
        )
    else:
        con.execute("UPDATE chat_messages SET is_deleted=1 WHERE shell_id=?", (shell_id,))
    con.execute(
        "UPDATE chat_sessions SET is_active=0 WHERE shell_id=? AND user_id=?",
        (shell_id, user_id)
    )
    con.commit()
    return {"ok": True}
