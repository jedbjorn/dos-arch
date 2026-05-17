"""Read skill content for an assigned shell — lazy-load surface."""
from fastapi import APIRouter, HTTPException, Depends

from api.common.db import get_db

router = APIRouter(tags=["skills"])


@router.get("/shells/{shell_id}/skills", summary="List skills assigned to a shell, with full content")
def get_shell_skills(shell_id: int, con = Depends(get_db)):
    rows = con.execute("""
        SELECT s.skill_id, s.name, s.description, s.file_path, s.category, s.content, s.command
        FROM skills s
        JOIN shell_skills ss ON ss.skill_id = s.skill_id
        WHERE ss.shell_id = ? AND s.is_deleted = 0
        ORDER BY s.category, s.name
    """, (shell_id,)).fetchall()
    return [dict(r) for r in rows]


@router.get("/shells/{shell_id}/skills/{name}", summary="Get one assigned skill by name")
def get_shell_skill_by_name(shell_id: int, name: str, con = Depends(get_db)):
    row = con.execute("""
        SELECT s.skill_id, s.name, s.description, s.category, s.content
        FROM skills s
        JOIN shell_skills ss ON ss.skill_id = s.skill_id
        WHERE ss.shell_id = ? AND s.name = ? AND s.is_deleted = 0
    """, (shell_id, name)).fetchone()
    if not row:
        raise HTTPException(404, f"Skill '{name}' not found or not assigned to this shell")
    return dict(row)


@router.get("/skills/token/{name}", summary="Resolve a token-category skill's content for a shell")
def get_token(name: str, shell_id: int, con = Depends(get_db)):
    row = con.execute("""
        SELECT s.content FROM skills s
        JOIN shell_skills ss ON ss.skill_id = s.skill_id
        WHERE s.name = ? AND s.category = 'token' AND s.is_deleted = 0 AND ss.shell_id = ?
    """, (name, shell_id)).fetchone()
    if not row:
        raise HTTPException(404, "Token not found or not assigned to this shell")
    return {"token": row["content"]}


@router.get("/skills/{skill_id}", summary="Get one skill by id (must be assigned to the requesting shell)")
def get_skill(skill_id: int, shell_id: int, con = Depends(get_db)):
    row = con.execute("""
        SELECT s.* FROM skills s
        JOIN shell_skills ss ON ss.skill_id = s.skill_id
        WHERE s.skill_id = ? AND s.is_deleted = 0 AND ss.shell_id = ?
    """, (skill_id, shell_id)).fetchone()
    if not row:
        raise HTTPException(404, "Skill not found or not assigned to this shell")
    return dict(row)
