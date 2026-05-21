"""Boot-document composition — the materialized per-shell system prompt.

`compose_boot_document` renders a shell's boot document — the full typed
section catalog (shell-prompt-renderer spec §02) — from DB state.
`rerender_boot_document` writes that render into `shells.boot_document`; the
API identity-write paths call it so the column stays fresh without DB
triggers (dos-arch decision #107).

`session_start_payload` is what `GET /shells/{id}/session-start` returns: the
materialized document plus a live Block-3 dynamic tail (datetime, flag count,
unread inbox) assembled per request. The dispatcher reads it in one call.
"""
from datetime import datetime, timezone
import sqlite3

from shell_render import assemble_catalog


def compose_boot_document(con: sqlite3.Connection, shell_id: int) -> str:
    """Render a shell's boot document — the full typed section catalog
    (shell-prompt-renderer spec §02) — from DB state. Pure: reads only.
    Raises ValueError if the shell does not exist.

    Materialized into `shells.boot_document` and read once per turn by the
    dispatcher. The catalog renders at the dialect of the shell's current
    model — that shapes the Tools and Output Shape sections; a model-less
    shell defaults to anthropic. The document stays correct across model
    switches because the chat-session handlers re-materialize it on a switch
    (`api/routers/shells.py`). Tools / Output are dialect-dependent but only
    model-switch-volatile, not per-turn — so they belong in this cacheable
    render, not the dynamic block. The live wall-clock and flag count stay
    the dynamic block's job (`_dynamic_block`)."""
    row = con.execute(
        "SELECT active_archive_id FROM shells WHERE shell_id=?", (shell_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"shell {shell_id} not found")
    # The shell's current tool dialect — from its most-recent model-bearing
    # chat session. No session, or a model-less one → anthropic, the default.
    model = con.execute(
        "SELECT m.name, m.tool_dialect FROM chat_sessions cs "
        "JOIN models m ON m.model_id = cs.model_id "
        "WHERE cs.shell_id=? ORDER BY cs.is_active DESC, cs.last_active DESC LIMIT 1",
        (shell_id,),
    ).fetchone()
    dialect = model["tool_dialect"] if model else "anthropic"
    runtime_ctx = {
        "datetime": datetime.now(),  # host-local — the BOOT line labels it "local"
        "session_id": "—",          # materialized doc — no session in scope
        "archive_id": row["active_archive_id"] or "—",
        "shell_id": shell_id,
        "model": model["name"] if model else None,
    }
    return assemble_catalog(con, shell_id, dialect=dialect, runtime_ctx=runtime_ctx)


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
