"""Boot-document composition — the materialized per-session system prompt.

`compose_boot_document` renders a chat session's boot document — the full
typed section catalog (shell-prompt-renderer spec §02) — from DB state.
`rerender_boot_document` writes that render into `chat_sessions.boot_document`;
the API session and identity-write paths call it so the column stays fresh
without DB triggers (substrate decision #123, refining #107).

`rerender_shell_sessions` fans a re-render across every active session of a
shell — used when shared shell identity (role, mandate, seed, L&S) changes.

`session_start_payload` is what the session-start route returns: the
materialized document plus a live Block-3 dynamic tail (datetime, flag count,
unread inbox) assembled per request. The dispatcher reads it in one call.
"""
from datetime import datetime, timezone
import sqlite3

from shell_render import assemble_catalog


def compose_boot_document(con: sqlite3.Connection, chat_session_id: str) -> str:
    """Render a chat session's boot document — the full typed section catalog
    (shell-prompt-renderer spec §02) — from DB state. Pure: reads only.
    Raises ValueError if the session does not exist.

    The boot document is per chat session (substrate decision #123): it
    renders at the dialect of the session's model — that shapes the Tools and
    Output Shape sections; a model-less session defaults to anthropic.
    Materialized into `chat_sessions.boot_document`, read once per turn by the
    dispatcher, and re-materialized in place on a model switch. The live
    wall-clock and flag count stay the dynamic block's job (`_dynamic_block`)."""
    sess = con.execute(
        "SELECT cs.shell_id, s.active_archive_id, m.name AS model_name, "
        "m.tool_dialect "
        "FROM chat_sessions cs "
        "JOIN shells s ON s.shell_id = cs.shell_id "
        "LEFT JOIN models m ON m.model_id = cs.model_id "
        "WHERE cs.chat_session_id=?",
        (chat_session_id,),
    ).fetchone()
    if sess is None:
        raise ValueError(f"chat session {chat_session_id} not found")
    runtime_ctx = {
        "datetime": datetime.now(),  # host-local — the BOOT line labels it "local"
        "session_id": chat_session_id,
        # archive_id stays deferred — shell_memory_archives is unpopulated and
        # the session-narrative writer is a separate parallel agent (CC-069).
        "archive_id": sess["active_archive_id"] or "—",
        "shell_id": sess["shell_id"],
        "model": sess["model_name"],
    }
    return assemble_catalog(
        con, sess["shell_id"],
        dialect=sess["tool_dialect"] or "anthropic",
        runtime_ctx=runtime_ctx,
    )


def rerender_boot_document(con: sqlite3.Connection, chat_session_id: str) -> str:
    """Recompose one chat session's boot document and write it to
    `chat_sessions.boot_document`. Does not commit — the calling handler owns
    the transaction. Returns the rendered document."""
    doc = compose_boot_document(con, chat_session_id)
    con.execute(
        "UPDATE chat_sessions SET boot_document=? WHERE chat_session_id=?",
        (doc, chat_session_id),
    )
    return doc


def rerender_shell_sessions(con: sqlite3.Connection, shell_id: int) -> None:
    """Re-render the boot document of every active chat session for a shell.
    Shell identity — role, mandate, seed, L&S — is shared across all of a
    shell's sessions, so an edit to it must refresh each live session's
    document. Does not commit."""
    for (sid,) in con.execute(
        "SELECT chat_session_id FROM chat_sessions WHERE shell_id=? AND is_active=1",
        (shell_id,),
    ).fetchall():
        rerender_boot_document(con, sid)


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


def session_start_payload(con: sqlite3.Connection, chat_session_id: str) -> dict:
    """The session-start body: the materialized boot document (Blocks 1-2,
    cacheable) plus a live dynamic tail (Block 3). If the column is NULL — a
    session created before materialization, or never written — it is rendered
    on the spot; the caller commits. Raises ValueError if the session does
    not exist."""
    row = con.execute(
        "SELECT shell_id, boot_document FROM chat_sessions WHERE chat_session_id=?",
        (chat_session_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"chat session {chat_session_id} not found")
    boot = row["boot_document"]
    if boot is None:
        boot = rerender_boot_document(con, chat_session_id)
    return {"boot_document": boot, "dynamic": _dynamic_block(con, row["shell_id"])}
