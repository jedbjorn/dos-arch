"""Shared section renderers for the shell boot-prompt render chain.

A shell's boot prompt is rendered from live DB state by two paths:

  * ``shell_core/scripts/run.py`` — the CLI launcher. Writes the rendered
    prompt to ``shells/<shortname>/CLAUDE.md`` for an interactive ``claude``.
  * ``shell_core/api/services/boot_document.py`` — the API path. Materializes
    ``shells.boot_document`` for the dispatcher (local / API-model shells).

Both compose from the *same* DB state, and several sections — identity,
seed, L&S, skills — were rendered by byte-identical copy-pasted functions in
each file. This module is the single home for those shared section
renderers: a change to how a section renders now lands once, not once per
renderer. The two paths still own their own section *ordering* and
*assembly*; only the shared building blocks are unified here.

This is the seam the shell-prompt-renderer spec (§01) builds the typed
section catalog on — keep new shared section renderers here.

Importable from both contexts: the API runs with ``shell_core/`` on
``PYTHONPATH`` (``PYTHONPATH=/substrate/shell_core``); ``run.py`` puts the
same directory on ``sys.path`` before importing this module.
"""
from __future__ import annotations

import sqlite3


def render_identity(shell_row: sqlite3.Row) -> str:
    """Markdown table of the shell's identity columns. Empty cells render '—'."""
    def cell(v: object) -> str:
        s = v.strip() if isinstance(v, str) else (v or "")
        return str(s) if s else "—"
    return (
        "| | |\n"
        "|---|---|\n"
        f"| **Name** | {cell(shell_row['display_name'])} |\n"
        f"| **Shortname** | {cell(shell_row['shortname'])} |\n"
        f"| **Partner** | {cell(shell_row['partner'])} |\n"
        f"| **Role** | {cell(shell_row['role'])} |\n"
        f"| **Mandate** | {cell(shell_row['mandate'])} |"
    )


def render_seed(con: sqlite3.Connection, shell_id: int) -> str:
    """The shell's live seed entries, oldest first, each headed by its date."""
    rows = con.execute(
        "SELECT entry_date, body FROM shell_identity_entries "
        "WHERE shell_id=? AND kind='seed' AND is_deleted=0 AND retired_at IS NULL "
        "ORDER BY entry_date, entry_id",
        (shell_id,),
    ).fetchall()
    if not rows:
        return "(none)"
    return "\n\n".join(f"### {r['entry_date']}\n{r['body']}" for r in rows)


def render_lns(con: sqlite3.Connection, shell_id: int) -> str:
    """The shell's live Lessons & Stances entries, oldest first."""
    rows = con.execute(
        "SELECT body FROM shell_identity_entries "
        "WHERE shell_id=? AND kind='lns' AND is_deleted=0 AND retired_at IS NULL "
        "ORDER BY entry_date, entry_id",
        (shell_id,),
    ).fetchall()
    if not rows:
        return "(none)"
    return "\n\n".join(r["body"] for r in rows)


def render_skills(con: sqlite3.Connection, shell_id: int) -> str:
    """The shell's granted skills as a name + first-line-of-description list."""
    rows = con.execute(
        "SELECT s.name, s.description FROM skills s "
        "JOIN shell_skills ss ON ss.skill_id = s.skill_id "
        "WHERE ss.shell_id=? AND s.is_deleted=0 ORDER BY s.name",
        (shell_id,),
    ).fetchall()
    if not rows:
        return "(none)"
    lines = []
    for r in rows:
        desc = (r["description"] or "").strip().splitlines()[0] if r["description"] else ""
        lines.append(f"- **{r['name']}** — {desc}")
    return "\n".join(lines)
