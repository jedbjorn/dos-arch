"""Boot-document composition — the materialized per-shell system prompt.

`compose_boot_document` renders a shell's stable boot payload (Blocks 1-2 of
the agnostic-runtime spec §5.1) from DB state. `rerender_boot_document` writes
that render into `shells.boot_document`; the API identity-write paths call it
so the column stays fresh without DB triggers (dos-arch decision #107).

`session_start_payload` is what `GET /shells/{id}/session-start` returns: the
materialized document plus a live Block-3 dynamic tail (datetime, flag count,
unread inbox) assembled per request. The dispatcher reads it in one call.
"""
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

# boot.md — universal SYSTEM OVERRIDE + LAWS preamble, same for every shell.
_BOOT_PREAMBLE_PATH = Path(__file__).resolve().parents[2] / "templates" / "boot.md"


def _identity_table(shell: sqlite3.Row) -> str:
    def cell(v: object) -> str:
        s = v.strip() if isinstance(v, str) else (v or "")
        return str(s) if s else "—"
    return (
        "| | |\n"
        "|---|---|\n"
        f"| **Name** | {cell(shell['display_name'])} |\n"
        f"| **Shortname** | {cell(shell['shortname'])} |\n"
        f"| **Partner** | {cell(shell['partner'])} |\n"
        f"| **Role** | {cell(shell['role'])} |\n"
        f"| **Mandate** | {cell(shell['mandate'])} |"
    )


def _render_seed(con: sqlite3.Connection, shell_id: int) -> str:
    rows = con.execute(
        "SELECT entry_date, body FROM shell_identity_entries "
        "WHERE shell_id=? AND kind='seed' AND is_deleted=0 AND retired_at IS NULL "
        "ORDER BY entry_date, entry_id",
        (shell_id,),
    ).fetchall()
    if not rows:
        return "(none)"
    return "\n\n".join(f"### {r['entry_date']}\n{r['body']}" for r in rows)


def _render_lns(con: sqlite3.Connection, shell_id: int) -> str:
    rows = con.execute(
        "SELECT body FROM shell_identity_entries "
        "WHERE shell_id=? AND kind='lns' AND is_deleted=0 AND retired_at IS NULL "
        "ORDER BY entry_date, entry_id",
        (shell_id,),
    ).fetchall()
    if not rows:
        return "(none)"
    return "\n\n".join(r["body"] for r in rows)


def _render_skills(con: sqlite3.Connection, shell_id: int) -> str:
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


def compose_boot_document(con: sqlite3.Connection, shell_id: int) -> str:
    """Render a shell's stable boot payload from DB state. Pure — reads only,
    no writes. Raises ValueError if the shell does not exist."""
    shell = con.execute(
        "SELECT display_name, shortname, partner, role, mandate, "
        "current_state, additional_prompt FROM shells WHERE shell_id=?",
        (shell_id,),
    ).fetchone()
    if shell is None:
        raise ValueError(f"shell {shell_id} not found")

    # <self> sentinel → this shell's id, so an operating-protocol template
    # cloned across shells still resolves api_* paths (e.g. /shells/<self>)
    # to the right shell. Mirrors run.py's CLI render.
    operating_protocol = (shell["additional_prompt"] or "").strip().replace(
        "<self>", str(shell_id))

    parts = [
        _BOOT_PREAMBLE_PATH.read_text().rstrip(),
        "",
        "## IDENTITY",
        "",
        _identity_table(shell),
        "",
        "---",
        "",
        "## OPERATING PROTOCOL",
        "",
        operating_protocol,
        "",
        "---",
        "",
        "## CURRENT STATE",
        "",
        (shell["current_state"] or "(none)").strip(),
        "",
        "---",
        "",
        "## SEED",
        "",
        _render_seed(con, shell_id),
        "",
        "---",
        "",
        "## LESSONS & STANCES",
        "",
        _render_lns(con, shell_id),
        "",
        "---",
        "",
        "## SKILLS",
        "",
        _render_skills(con, shell_id),
        "",
    ]
    return "\n".join(parts)


def rerender_boot_document(con: sqlite3.Connection, shell_id: int) -> str:
    """Recompose the boot document and write it to `shells.boot_document`.
    Does not commit — the calling handler owns the transaction. Returns the
    rendered document."""
    doc = compose_boot_document(con, shell_id)
    con.execute("UPDATE shells SET boot_document=? WHERE shell_id=?", (doc, shell_id))
    return doc


def _dynamic_block(con: sqlite3.Connection, shell_id: int) -> dict:
    """Block 3 — the volatile tail, assembled live per request. Never cached."""
    flags_open = con.execute(
        "SELECT COUNT(*) FROM flags WHERE shell_id=? AND resolved=0 AND is_deleted=0",
        (shell_id,),
    ).fetchone()[0]
    unread = con.execute(
        "SELECT message_id, sender_id, subject, body, sent_at FROM shell_messages "
        "WHERE recipient_id=? AND read=0 ORDER BY sent_at ASC",
        (shell_id,),
    ).fetchall()
    return {
        "datetime_utc": datetime.now(timezone.utc).isoformat(),
        "flags_open": flags_open,
        "unread_messages": [dict(r) for r in unread],
    }


def session_start_payload(con: sqlite3.Connection, shell_id: int) -> dict:
    """The `GET /session-start` body: the materialized boot document (Blocks
    1-2, cacheable) plus a live dynamic tail (Block 3). If the column is NULL
    — a shell created before materialization, or never written — it is
    rendered on the spot; the caller commits."""
    row = con.execute(
        "SELECT boot_document FROM shells WHERE shell_id=?", (shell_id,)
    ).fetchone()
    boot = row["boot_document"]
    if boot is None:
        boot = rerender_boot_document(con, shell_id)
    return {"boot_document": boot, "dynamic": _dynamic_block(con, shell_id)}
