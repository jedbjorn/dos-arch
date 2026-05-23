"""Admin operations — shell assignment, skill attachment, browser-chat targeting, catalogue-sync health."""
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel
import json
import sqlite3

from api.common.db import get_db
from api.common.auth import _require_admin

router = APIRouter(tags=["admin"])


@router.get("/admin/shells", summary="Admin: list all shells with assigned user, skills, and tokens")
def admin_get_shells(request: Request, con = Depends(get_db)):
    _require_admin(request)
    shells = con.execute(
        """SELECT sh.shell_id, sh.display_name, sh.user_id, sh.browser_chat,
                  u.display_name AS partner_name
           FROM shells sh
           LEFT JOIN users u ON sh.user_id = u.user_id
           WHERE sh.shell_id > 0
           ORDER BY sh.shell_id"""
    ).fetchall()
    result = []
    for shell in shells:
        skills = con.execute("""
            SELECT s.skill_id, s.name, s.description, s.category
            FROM skills s JOIN shell_skills ss ON s.skill_id = ss.skill_id
            WHERE ss.shell_id = ? AND s.category != 'token' AND s.is_deleted = 0
            ORDER BY s.category, s.name
        """, (shell["shell_id"],)).fetchall()
        tokens = con.execute("""
            SELECT s.skill_id, s.name, s.description
            FROM skills s JOIN shell_skills ss ON s.skill_id = ss.skill_id
            WHERE ss.shell_id = ? AND s.category = 'token' AND s.is_deleted = 0
            ORDER BY s.name
        """, (shell["shell_id"],)).fetchall()
        result.append({
            **dict(shell),
            "skills": [dict(r) for r in skills],
            "tokens": [dict(r) for r in tokens],
        })
    return result


class AssignShellUserBody(BaseModel):
    user_id: int | None = None


@router.patch("/admin/shells/{shell_id}/assign-user", summary="Admin: assign or unassign a user to a shell")
def admin_assign_shell_user(request: Request, shell_id: int, body: AssignShellUserBody, con = Depends(get_db)):
    _require_admin(request)
    if not con.execute("SELECT 1 FROM shells WHERE shell_id=?", (shell_id,)).fetchone():
        raise HTTPException(404, "Shell not found")
    if body.user_id is not None:
        if not con.execute("SELECT 1 FROM users WHERE user_id=?", (body.user_id,)).fetchone():
            raise HTTPException(404, "User not found")
    con.execute("UPDATE shells SET user_id=? WHERE shell_id=?", (body.user_id, shell_id))
    con.commit()
    return {"ok": True}


@router.patch("/admin/shells/{shell_id}/browser-chat", summary="Admin: toggle which shell is the user's browser-chat target")
def admin_toggle_browser_chat(request: Request, shell_id: int, con = Depends(get_db)):
    _require_admin(request)
    shell = con.execute("SELECT shell_id, user_id, browser_chat FROM shells WHERE shell_id=?", (shell_id,)).fetchone()
    if not shell:
        raise HTTPException(404, "Shell not found")
    if not shell["user_id"]:
        raise HTTPException(400, "Shell has no assigned user")
    new_val = 0 if shell["browser_chat"] else 1
    if new_val == 1:
        con.execute("UPDATE shells SET browser_chat=0 WHERE user_id=? AND shell_id!=?", (shell["user_id"], shell_id))
    con.execute("UPDATE shells SET browser_chat=? WHERE shell_id=?", (new_val, shell_id))
    con.commit()
    return {"shell_id": shell_id, "browser_chat": bool(new_val)}


@router.get("/admin/skills/available", summary="Admin: list non-token skills available for assignment")
def admin_available_skills(request: Request, con = Depends(get_db)):
    _require_admin(request)
    rows = con.execute(
        "SELECT skill_id, name, description, category, common FROM skills WHERE category != 'token' AND is_deleted = 0 ORDER BY category, name"
    ).fetchall()
    return [dict(r) for r in rows]


@router.get("/admin/skills/{skill_id}", summary="Admin: fetch one skill (incl. content) for preview")
def admin_get_skill(request: Request, skill_id: int, con = Depends(get_db)):
    _require_admin(request)
    row = con.execute(
        "SELECT skill_id, name, description, category, common, content "
        "FROM skills WHERE skill_id=? AND is_deleted=0",
        (skill_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Skill not found")
    return dict(row)


@router.get("/admin/tokens/available", summary="Admin: list available token-category skills")
def admin_available_tokens(request: Request, con = Depends(get_db)):
    _require_admin(request)
    rows = con.execute(
        "SELECT skill_id, name, description FROM skills WHERE category = 'token' AND is_deleted = 0 ORDER BY name"
    ).fetchall()
    return [dict(r) for r in rows]


class ShellSkillBody(BaseModel):
    skill_id: int


@router.post("/admin/shells/{shell_id}/skills", summary="Admin: assign a skill to a shell")
def admin_add_shell_skill(request: Request, shell_id: int, body: ShellSkillBody, con = Depends(get_db)):
    _require_admin(request)
    if not con.execute("SELECT 1 FROM shells WHERE shell_id=?", (shell_id,)).fetchone():
        raise HTTPException(404, "Shell not found")
    if not con.execute("SELECT 1 FROM skills WHERE skill_id=? AND is_deleted=0",
                        (body.skill_id,)).fetchone():
        raise HTTPException(404, "Skill not found")
    # Any skill is assignable to any shell. Skill-scoped tooling makes a
    # shell's skill set per-shell by design — there is no common-only
    # restriction; the boot document picks the change up on its next render.
    try:
        con.execute("INSERT INTO shell_skills (shell_id, skill_id) VALUES (?,?)", (shell_id, body.skill_id))
        con.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Already assigned")
    return {"ok": True}


@router.delete("/admin/shells/{shell_id}/skills/{skill_id}", summary="Admin: remove a skill from a shell")
def admin_remove_shell_skill(request: Request, shell_id: int, skill_id: int, con = Depends(get_db)):
    _require_admin(request)
    con.execute("DELETE FROM shell_skills WHERE shell_id=? AND skill_id=?", (shell_id, skill_id))
    con.commit()
    return {"ok": True}


# ── Skill catalogue CRUD ──────────────────────────────────────────────────────

class CreateSkillBody(BaseModel):
    name:        str
    description: str = ""
    category:    str = "workflow"
    content:     str
    command:     str | None = None
    common:      int = 0


@router.post("/admin/skills", summary="Admin: create a new skill")
def admin_create_skill(request: Request, body: CreateSkillBody, con = Depends(get_db)):
    _require_admin(request)
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "name is required")
    if con.execute("SELECT 1 FROM skills WHERE name=? AND is_deleted=0", (name,)).fetchone():
        raise HTTPException(409, f"skill '{name}' already exists")
    cur = con.execute(
        "INSERT INTO skills (name, description, category, content, command, common, is_deleted) "
        "VALUES (?, ?, ?, ?, ?, ?, 0)",
        (name, body.description, body.category, body.content,
         (body.command or None), 1 if body.common else 0),
    )
    con.commit()
    return {"skill_id": cur.lastrowid, "name": name}


class UpdateSkillBody(BaseModel):
    description: str | None = None
    category:    str | None = None
    content:     str | None = None
    command:     str | None = None
    common:      int | None = None


@router.patch("/admin/skills/{skill_id}", summary="Admin: update a skill's content or metadata")
def admin_update_skill(request: Request, skill_id: int, body: UpdateSkillBody, con = Depends(get_db)):
    _require_admin(request)
    if not con.execute("SELECT 1 FROM skills WHERE skill_id=? AND is_deleted=0", (skill_id,)).fetchone():
        raise HTTPException(404, "Skill not found")
    fields, args = [], []
    for col in ("description", "category", "content", "command"):
        val = getattr(body, col)
        if val is not None:
            fields.append(f"{col}=?"); args.append(val)
    if body.common is not None:
        fields.append("common=?"); args.append(1 if body.common else 0)
    if not fields:
        raise HTTPException(422, "no fields to update")
    args.append(skill_id)
    con.execute(f"UPDATE skills SET {', '.join(fields)} WHERE skill_id=?", args)
    con.commit()
    return {"ok": True, "skill_id": skill_id}


@router.delete("/admin/skills/{skill_id}", summary="Admin: soft-delete a skill (is_deleted=1; row preserved)")
def admin_delete_skill(request: Request, skill_id: int, con = Depends(get_db)):
    _require_admin(request)
    if not con.execute("SELECT 1 FROM skills WHERE skill_id=? AND is_deleted=0", (skill_id,)).fetchone():
        raise HTTPException(404, "Skill not found")
    con.execute("UPDATE skills SET is_deleted=1 WHERE skill_id=?", (skill_id,))
    con.commit()
    return {"ok": True, "skill_id": skill_id}


_SYNC_COLS = ("run_id, run_at, trigger_kind, surfaces, total_insert, "
              "total_update, had_error, error")


def _sync_row(r):
    """dr_sync_runs row → dict, with the surfaces JSON string decoded to an object."""
    d = dict(r)
    try:
        d["surfaces"] = json.loads(d["surfaces"]) if d.get("surfaces") else {}
    except (ValueError, TypeError):
        pass  # leave the raw string if it somehow isn't valid JSON
    return d


@router.get("/admin/catalogue-sync", summary="Admin: dr_* catalogue sync health — recent runs + staleness check")
def admin_catalogue_sync(request: Request, con = Depends(get_db)):
    """Health view over dr_sync_runs — the dr_* catalogue sync audit log.

    `stale` is the cron-didn't-fire signal: true when no cron run has landed in
    the last 26h (a 24h cron + slack), or none ever has. A run that never
    started leaves no row, so staleness is computed from absence, not a flag.
    """
    _require_admin(request)
    runs = con.execute(
        f"SELECT {_SYNC_COLS} FROM dr_sync_runs ORDER BY run_id DESC LIMIT 20"
    ).fetchall()
    last_cron = con.execute(
        f"SELECT {_SYNC_COLS} FROM dr_sync_runs WHERE trigger_kind='cron' "
        "ORDER BY run_id DESC LIMIT 1"
    ).fetchone()
    fresh_cron = con.execute(
        "SELECT 1 FROM dr_sync_runs WHERE trigger_kind='cron' "
        "AND run_at >= datetime('now','-26 hours') LIMIT 1"
    ).fetchone()
    recent_errors = con.execute(
        "SELECT COUNT(*) FROM dr_sync_runs WHERE had_error=1 "
        "AND run_at >= datetime('now','-7 days')"
    ).fetchone()[0]
    return {
        "latest":        _sync_row(runs[0]) if runs else None,
        "last_cron":     _sync_row(last_cron) if last_cron else None,
        "stale":         fresh_cron is None,
        "recent_errors": recent_errors,
        "runs":          [_sync_row(r) for r in runs],
    }
