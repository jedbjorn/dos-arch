"""Admin operations — user + shell management, skill/tool attachment, browser-chat targeting, catalogue-sync health."""
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel
import hashlib
import json
import re
import secrets
import sqlite3

from api.common.db import get_db
from api.common.auth import _require_admin
from api.common import broker

router = APIRouter(tags=["admin"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_EXP_PRIME_SHORT = "exprime"


def _mint_exp_shell(con: sqlite3.Connection, user_id: int) -> dict:
    """Mint an assistant shell (Exp-NN) for a new user — a clone of Exp-Prime's
    base (role/mandate + skill/tool grants); identity (seed/L&S/memory) starts
    blank. The full template-sync model is deferred (flag CC-106 era); this
    copies the current grants by value so the new shell boots with Prime's kit."""
    rows = con.execute("SELECT display_name FROM shells WHERE display_name LIKE 'Exp-%'").fetchall()
    nums = [int(m.group(1)) for r in rows
            if (m := re.match(r"Exp-(\d+)$", r["display_name"] or ""))]
    n = (max(nums) + 1) if nums else 1
    display, short = f"Exp-{n}", f"exp{n}"

    prime = con.execute(
        "SELECT shell_id, role, mandate FROM shells WHERE shortname=?",
        (_EXP_PRIME_SHORT,)).fetchone()
    role = prime["role"] if prime else None
    mandate = prime["mandate"] if prime else None

    api_key = secrets.token_urlsafe(32)
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    cur = con.execute(
        "INSERT INTO shells (display_name, shortname, role, mandate, user_id, "
        "browser_chat, is_shared, is_admin, api_auth, api_key, api_key_hash) "
        "VALUES (?, ?, ?, ?, ?, 1, 0, 0, 1, ?, ?)",
        (display, short, role, mandate, user_id, api_key, api_key_hash),
    )
    new_id = cur.lastrowid
    if prime:
        con.execute(
            "INSERT OR IGNORE INTO shell_skills (shell_id, skill_id) "
            "SELECT ?, skill_id FROM shell_skills WHERE shell_id=?",
            (new_id, prime["shell_id"]))
        con.execute(
            "INSERT OR IGNORE INTO shell_tools (shell_id, tool_id) "
            "SELECT ?, tool_id FROM skill_tools "
            "WHERE skill_id IN (SELECT skill_id FROM shell_skills WHERE shell_id=?)",
            (new_id, new_id))
    return {"shell_id": new_id, "display_name": display, "shortname": short}


class CreateUserBody(BaseModel):
    email:    str
    is_admin: int = 0


@router.post("/admin/users", summary="Admin: create a user (broker auth_user + app row + Exp-NN). Returns the one-time password.")
def admin_create_user(request: Request, body: CreateUserBody, con=Depends(get_db)):
    _require_admin(request)
    email = body.email.strip()
    if not _EMAIL_RE.match(email):
        raise HTTPException(422, "A valid email is required (it is the login identifier).")
    if con.execute("SELECT 1 FROM users WHERE email=? COLLATE NOCASE", (email,)).fetchone():
        raise HTTPException(409, "A user with that email already exists.")

    # 1) broker creates the credential record (random password, returned once).
    bstat, bres = broker.post("/admin/auth/users", {"email": email})
    if bstat == 409:
        raise HTTPException(409, "Those credentials already exist in the auth backend.")
    if bstat != 200 or "account_id" not in bres:
        raise HTTPException(502, "Auth backend failed to create the user.")
    account_id, password = bres["account_id"], bres["password"]

    # 2) app relational row, related by account_id (no cross-DB FK).
    try:
        cur = con.execute(
            "INSERT INTO users (username, email, account_id, is_admin, is_active) "
            "VALUES (?, ?, ?, ?, 1)",
            (email, email, account_id, 1 if body.is_admin else 0))
        user_id = cur.lastrowid
        # 3) auto-mint the user's assistant shell.
        shell = _mint_exp_shell(con, user_id)
        con.execute(
            "INSERT INTO auth_events (user_id, account_id, email, kind, detail) "
            "VALUES (?, ?, ?, 'user_create', ?)",
            (user_id, account_id, email, shell["shortname"]))
        con.commit()
    except Exception:
        con.rollback()
        # The broker auth_user is now an orphan (no app-side delete-user yet);
        # acceptable at invite-only scale — re-running with the same email 409s
        # and an operator can reconcile. Surfaced rather than silently swallowed.
        raise HTTPException(500, "User creation failed after the credential was provisioned; reconcile the auth backend.")

    return {"user_id": user_id, "email": email, "account_id": account_id,
            "password": password, "is_admin": bool(body.is_admin), "shell": shell}


@router.get("/admin/users/full", summary="Admin: full user directory (email, admin, TOTP, shell count)")
def admin_list_users(request: Request, con=Depends(get_db)):
    _require_admin(request)
    rows = con.execute(
        """SELECT u.user_id, u.username, u.email, u.initials, u.is_admin, u.is_active,
                  (u.account_id IS NOT NULL)    AS provisioned,
                  (u.totp_enrolled_at IS NOT NULL) AS totp_enrolled,
                  (SELECT COUNT(*) FROM shells s WHERE s.user_id = u.user_id) AS shell_count
           FROM users u ORDER BY u.user_id"""
    ).fetchall()
    return [dict(r) for r in rows]


class SetAdminBody(BaseModel):
    is_admin: int


@router.patch("/admin/users/{user_id}/admin", summary="Admin: grant/revoke a user's admin flag (last-admin guarded)")
def admin_set_user_admin(request: Request, user_id: int, body: SetAdminBody, con=Depends(get_db)):
    _require_admin(request)
    row = con.execute("SELECT is_admin FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        raise HTTPException(404, "User not found")
    new_val = 1 if body.is_admin else 0
    if row["is_admin"] and not new_val:
        # Lockout guard: never clear the last remaining (active) admin.
        others = con.execute(
            "SELECT COUNT(*) FROM users WHERE is_admin=1 AND is_active=1 AND user_id!=?",
            (user_id,)).fetchone()[0]
        if others == 0:
            raise HTTPException(409, "Cannot remove the last admin.")
    con.execute("UPDATE users SET is_admin=? WHERE user_id=?", (new_val, user_id))
    con.execute(
        "INSERT INTO auth_events (user_id, kind, detail) VALUES (?, 'admin_toggle', ?)",
        (user_id, f"is_admin={new_val}"))
    con.commit()
    return {"user_id": user_id, "is_admin": bool(new_val)}


@router.post("/admin/users/{user_id}/reset-auth", summary="Admin-assisted recovery: rotate the user's password AND reset TOTP. Returns the new one-time password.")
def admin_reset_user_auth(request: Request, user_id: int, con=Depends(get_db)):
    _require_admin(request)
    row = con.execute("SELECT account_id, email FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        raise HTTPException(404, "User not found")
    if not row["account_id"]:
        raise HTTPException(409, "User has no provisioned credential to reset.")
    # The broker (credential authority) mints + hashes a fresh password AND clears
    # TOTP atomically, returning the plaintext once; the app never sees or stores
    # password material. This is the locked-out-user recovery path: new password +
    # TOTP re-enrollment on next login.
    bstat, bres = broker.post("/admin/auth/reset-user-auth", {"account_id": row["account_id"]})
    if bstat == 404:
        raise HTTPException(502, "Auth backend has no matching credential for this user.")
    if bstat != 200 or "password" not in bres:
        raise HTTPException(502, "Auth backend failed to reset the user's auth.")
    # Keep the app-side enrollment mirror consistent with the broker (TOTP now cleared).
    con.execute("UPDATE users SET totp_enrolled_at=NULL WHERE user_id=?", (user_id,))
    con.execute(
        "INSERT INTO auth_events (user_id, account_id, email, kind, detail) "
        "VALUES (?, ?, ?, 'auth_reset', 'admin: password + totp')",
        (user_id, row["account_id"], row["email"]))
    con.commit()
    return {"user_id": user_id, "email": row["email"], "password": bres["password"]}


@router.get("/admin/shells", summary="Admin: list all shells with assigned user, skills, and tokens")
def admin_get_shells(request: Request, con = Depends(get_db)):
    _require_admin(request)
    shells = con.execute(
        """SELECT sh.shell_id, sh.display_name, sh.user_id, sh.browser_chat,
                  sh.api_key_rotated_at,
                  (sh.api_key_hash IS NOT NULL) AS has_key,
                  u.username AS partner_name
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


@router.post("/admin/shells/{shell_id}/rotate-key", summary="Admin: rotate a shell's substrate-API key")
def admin_rotate_shell_key(request: Request, shell_id: int, con = Depends(get_db)):
    _require_admin(request)
    if not con.execute("SELECT 1 FROM shells WHERE shell_id=?", (shell_id,)).fetchone():
        raise HTTPException(404, "Shell not found")
    # rotate_key writes api_key + api_key_hash + api_key_rotated_at atomically.
    # The new plaintext is NOT returned: the dispatcher reads it straight from
    # the DB on its next turn, so nothing needs it relayed through HTTP.
    import sys as _sys
    from pathlib import Path
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    _sys.path.insert(0, str(scripts_dir))
    try:
        from ensure_api_keys import rotate_key  # type: ignore[import-not-found]
        rotate_key(con, shell_id)
        con.commit()
    finally:
        if str(scripts_dir) in _sys.path:
            _sys.path.remove(str(scripts_dir))
    row = con.execute(
        "SELECT api_key_rotated_at FROM shells WHERE shell_id=?", (shell_id,)
    ).fetchone()
    return {"shell_id": shell_id, "api_key_rotated_at": row["api_key_rotated_at"]}


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
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Already assigned")
    # Materialise the skill's required tools into shell_tools (migration 056).
    # INSERT OR IGNORE so already-granted tools are left alone; the user can
    # toggle any of these off afterwards (they are plain direct grants now).
    con.execute(
        "INSERT OR IGNORE INTO shell_tools (shell_id, tool_id) "
        "SELECT ?, tool_id FROM skill_tools WHERE skill_id=?",
        (shell_id, body.skill_id),
    )
    con.commit()
    return {"ok": True}


@router.delete("/admin/shells/{shell_id}/skills/{skill_id}", summary="Admin: remove a skill from a shell")
def admin_remove_shell_skill(request: Request, shell_id: int, skill_id: int, con = Depends(get_db)):
    _require_admin(request)
    # Only the skill grant is removed. Tools materialised from it stay as
    # direct shell_tools grants (freely toggleable) — removing a skill does not
    # strip tools the shell may now depend on. Drop them explicitly in the
    # Tools tab if unwanted. (Migration 056 grant model.)
    con.execute("DELETE FROM shell_skills WHERE shell_id=? AND skill_id=?", (shell_id, skill_id))
    con.commit()
    return {"ok": True}


# ── Tool catalogue + per-shell tool grants ────────────────────────────────────

@router.get("/admin/tools/available", summary="Admin: list all active tools available for assignment")
def admin_available_tools(request: Request, con = Depends(get_db)):
    _require_admin(request)
    rows = con.execute(
        "SELECT tool_id, name, description, kind, is_general, status "
        "FROM tools WHERE status='active' ORDER BY is_general DESC, name"
    ).fetchall()
    return [dict(r) for r in rows]


@router.get("/admin/tools/{tool_id}", summary="Admin: fetch one tool (incl. spec) for preview")
def admin_get_tool(request: Request, tool_id: int, con = Depends(get_db)):
    _require_admin(request)
    row = con.execute(
        "SELECT tool_id, name, description, kind, spec, handler, is_general, status "
        "FROM tools WHERE tool_id=?",
        (tool_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Tool not found")
    return dict(row)


class ShellToolBody(BaseModel):
    tool_id: int


@router.post("/admin/shells/{shell_id}/tools", summary="Admin: assign a tool to a shell")
def admin_add_shell_tool(request: Request, shell_id: int, body: ShellToolBody, con = Depends(get_db)):
    _require_admin(request)
    if not con.execute("SELECT 1 FROM shells WHERE shell_id=?", (shell_id,)).fetchone():
        raise HTTPException(404, "Shell not found")
    tool = con.execute("SELECT is_general FROM tools WHERE tool_id=? AND status='active'",
                       (body.tool_id,)).fetchone()
    if not tool:
        raise HTTPException(404, "Tool not found")
    if tool["is_general"]:
        raise HTTPException(409, "General tools are granted to every shell — no per-shell assignment")
    try:
        con.execute("INSERT INTO shell_tools (shell_id, tool_id) VALUES (?,?)", (shell_id, body.tool_id))
        con.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Already assigned")
    return {"ok": True}


@router.delete("/admin/shells/{shell_id}/tools/{tool_id}", summary="Admin: remove a tool from a shell")
def admin_remove_shell_tool(request: Request, shell_id: int, tool_id: int, con = Depends(get_db)):
    _require_admin(request)
    con.execute("DELETE FROM shell_tools WHERE shell_id=? AND tool_id=?", (shell_id, tool_id))
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
