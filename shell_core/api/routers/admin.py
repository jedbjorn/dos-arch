"""Admin operations — shell assignment, skill attachment, browser-chat targeting."""
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel
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


@router.get("/admin/tokens/available", summary="Admin: list available token-category skills")
def admin_available_tokens(request: Request, con = Depends(get_db)):
    _require_admin(request)
    rows = con.execute(
        "SELECT skill_id, name, description FROM skills WHERE category = 'token' AND is_deleted = 0 ORDER BY name"
    ).fetchall()
    return [dict(r) for r in rows]


class ShellSkillBody(BaseModel):
    skill_id: int


@router.post("/admin/shells/{shell_id}/skills", summary="Admin: assign a skill to a shell (live shells require common=1)")
def admin_add_shell_skill(request: Request, shell_id: int, body: ShellSkillBody, con = Depends(get_db)):
    _require_admin(request)
    shell = con.execute("SELECT shell_id, browser_chat FROM shells WHERE shell_id=?", (shell_id,)).fetchone()
    if not shell:
        raise HTTPException(404, "Shell not found")
    skill = con.execute("SELECT skill_id, common FROM skills WHERE skill_id=? AND is_deleted=0", (body.skill_id,)).fetchone()
    if not skill:
        raise HTTPException(404, "Skill not found")
    if shell["browser_chat"] and not skill["common"]:
        raise HTTPException(400, "Live (browser-chat) shells can only be assigned common=1 skills")
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
