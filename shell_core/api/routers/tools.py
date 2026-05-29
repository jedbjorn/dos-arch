"""Read a shell's granted tools — the per-shell view surface for the /shells UI.

A shell's effective tool set is the general tools (tools.is_general=1, every
shell) plus its direct grants (shell_tools — which include the tools
materialised from each skill it holds). This router exposes the direct grants
with, for each, the held skills that require it (the "via <skill>" hint). The
general tools come from /admin/tools/available (is_general flag); the catalogue
CRUD + assignment endpoints live in admin.py. (Migration 056.)"""
from fastapi import APIRouter, Depends

from api.common.db import get_db

router = APIRouter(tags=["tools"])


@router.get("/shells/{shell_id}/tools", summary="List a shell's directly-granted tools, with the held skills that require each")
def get_shell_tools(shell_id: int, con = Depends(get_db)):
    rows = con.execute("""
        SELECT t.tool_id, t.name, t.description, t.kind, t.spec, t.is_general
        FROM tools t
        JOIN shell_tools st ON st.tool_id = t.tool_id
        WHERE st.shell_id = ? AND t.status = 'active'
        ORDER BY t.name
    """, (shell_id,)).fetchall()
    out = []
    for r in rows:
        required_by = [x["name"] for x in con.execute("""
            SELECT s.name
            FROM skill_tools kt
            JOIN skills s ON s.skill_id = kt.skill_id
            JOIN shell_skills ss ON ss.skill_id = kt.skill_id AND ss.shell_id = ?
            WHERE kt.tool_id = ? AND s.is_deleted = 0
            ORDER BY s.name
        """, (shell_id, r["tool_id"])).fetchall()]
        d = dict(r)
        d["required_by"] = required_by
        out.append(d)
    return out
