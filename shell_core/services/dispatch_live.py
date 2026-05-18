#!/usr/bin/env python3
"""dispatch_live.py — the browser-chat dispatcher.

Ported from ExpLive (designs_os). Polls `chat_messages` for unread inbound
rows, runs a multi-turn Anthropic Messages loop with `api_*` tools, and posts
the final assistant text via `POST /shells/{id}/chat/reply`.

dos-arch port (CC-47, decision #108):
  - Anthropic-only — the ProviderAdapter seam (agnostic-runtime §3.4) is the
    next phase (A0); this speaks the Anthropic SDK directly.
  - No auth — dos-arch's API is open on localhost in alpha; the `X-API-Key`
    machinery is not ported. Required before any off-localhost exposure (CC-55).
  - Tokens only, no cost — `chat_messages.tokens` carries the per-turn total;
    cost varies per provider and is meaningless for local models.
  - Context is the materialized boot document: one `GET /session-start` call
    returns `{boot_document, dynamic}` — Block 1-2 cached, Block 3 live.

A shell joins the dispatcher by having `shells.browser_chat = 1`.

Run:  python3 shell_core/services/dispatch_live.py
Env:  ANTHROPIC_API_KEY (required), DISPATCH_API_BASE, DISPATCH_MODEL,
      DISPATCH_DB_PATH, DISPATCH_POOL_WORKERS, DISPATCH_TOOL_CONCURRENCY
"""

import concurrent.futures
import fcntl
import json
import os
import signal
import sqlite3
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import anthropic

# ── Config ────────────────────────────────────────────────────────────────────

_REPO = Path(__file__).resolve().parents[2]
DB_PATH       = os.environ.get("DISPATCH_DB_PATH", str(_REPO / "shell_core" / "shell_db.db"))
API_BASE      = os.environ.get("DISPATCH_API_BASE", "http://127.0.0.1:8000").rstrip("/")
MODEL         = os.environ.get("DISPATCH_MODEL", "claude-sonnet-4-6")
LOCKFILE_PATH = str(Path(__file__).resolve().parent / ".dispatch_live.lock")

POLL_MS                = 250
MAX_TOKENS             = 16384
MAX_TOOL_ITER          = 20
DEFAULT_HISTORY_WINDOW = 25          # fallback if users.chat_history_window unset
POOL_WORKERS           = int(os.environ.get("DISPATCH_POOL_WORKERS", "5"))
TOOL_CONCURRENCY       = int(os.environ.get("DISPATCH_TOOL_CONCURRENCY", "20"))
STUCK_SESSION_SEC      = 300         # warn if a session is in-flight this long

# Process-wide cap on in-flight API calls from execute_tool — N workers × 20
# tool iterations could otherwise saturate our own API.
TOOL_SEMAPHORE = threading.Semaphore(TOOL_CONCURRENCY)

TOOLS = [
    {
        "name": "api_get",
        "description": f"GET request to the dos-arch API at {API_BASE}. Path may include a query string. Returns the response body as text.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": 'API path including query, must start with /. e.g. "/shells/2/decisions"'},
            },
            "required": ["path"],
        },
    },
    {
        "name": "api_post",
        "description": "POST request to the dos-arch API. Body sent as JSON.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "body": {"type": "object", "description": "JSON body."},
            },
            "required": ["path", "body"],
        },
    },
    {
        "name": "api_patch",
        "description": "PATCH request to the dos-arch API. Body sent as JSON.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "body": {"type": "object"},
            },
            "required": ["path", "body"],
        },
    },
    {
        "name": "api_delete",
        "description": "DELETE request to the dos-arch API. Optional JSON body.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "body": {"type": "object", "description": "Optional JSON body."},
            },
            "required": ["path"],
        },
    },
]

METHOD_MAP = {"api_get": "GET", "api_post": "POST", "api_patch": "PATCH", "api_delete": "DELETE"}


# ── DB ──────────────────────────────────────────────────────────────────────--

def db() -> sqlite3.Connection:
    # check_same_thread=False is defensive — per-thread connections do not
    # actually cross threads. timeout=10 sets sqlite3 busy_timeout to 10s.
    con = sqlite3.connect(DB_PATH, timeout=10.0, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def discover_browser_shell_ids(con: sqlite3.Connection) -> list[int]:
    rows = con.execute(
        "SELECT shell_id FROM shells WHERE browser_chat=1 ORDER BY shell_id"
    ).fetchall()
    return [r[0] for r in rows]


def load_shell(con: sqlite3.Connection, shell_id: int):
    return con.execute(
        "SELECT shell_id, display_name FROM shells WHERE shell_id=?", (shell_id,)
    ).fetchone()


def load_user_history_window(con: sqlite3.Connection, user_id) -> int:
    if not user_id:
        return DEFAULT_HISTORY_WINDOW
    row = con.execute(
        "SELECT chat_history_window FROM users WHERE user_id=?", (user_id,)
    ).fetchone()
    return row["chat_history_window"] if row and row["chat_history_window"] else DEFAULT_HISTORY_WINDOW


def load_history(con: sqlite3.Connection, chat_session_id, window: int) -> list[dict]:
    # sent_at has 1-sec granularity — message_id tiebreaker keeps order stable.
    rows = con.execute(
        "SELECT direction, body FROM ("
        "  SELECT direction, body, sent_at, message_id FROM chat_messages "
        "  WHERE chat_session_id=? AND is_deleted=0 "
        "  ORDER BY sent_at DESC, message_id DESC LIMIT ?"
        ") ORDER BY sent_at ASC, message_id ASC",
        (chat_session_id, window),
    ).fetchall()
    msgs = [
        {"role": "user" if r["direction"] == "inbound" else "assistant", "content": r["body"]}
        for r in rows
    ]
    # Anthropic Messages API requires messages[0].role == 'user'.
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    return msgs


def fetch_unread_for_shell(con: sqlite3.Connection, shell_id: int):
    return con.execute(
        "SELECT message_id, shell_id, user_id, body, chat_session_id "
        "FROM chat_messages WHERE shell_id=? "
        "AND direction='inbound' AND read_by_shell=0 AND is_deleted=0 "
        "ORDER BY sent_at ASC, message_id ASC",
        (shell_id,),
    ).fetchall()


# ── HTTP to our own API ─────────────────────────────────────────────────────--

def _request(method: str, path: str, body=None, timeout: int = 30):
    """One HTTP call to the dos-arch API. Returns (text, is_error)."""
    if not path.startswith("/"):
        path = "/" + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = urllib.request.Request(API_BASE + path, data=data, method=method, headers=headers)
    for attempt in range(3):
        if attempt > 0:
            time.sleep(0.5 * (2 ** attempt))  # 1s, 2s
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode(), False
        except urllib.error.HTTPError as e:
            # Retry 429/503; other 4xx won't be helped by a retry.
            if e.code in (429, 503) and attempt < 2:
                continue
            return f"HTTP {e.code}: {e.read().decode()[:1500]}", True
        except (urllib.error.URLError, ConnectionResetError) as e:
            if attempt < 2:
                continue
            return f"error: {type(e).__name__}: {e}", True
        except Exception as e:
            return f"error: {type(e).__name__}: {e}", True
    return "error: retries exhausted", True


def fetch_session_start(shell_id: int) -> dict:
    """GET the materialized boot document + live dynamic tail. Returns the
    decoded payload, or {'error': ...} if the call fails."""
    text, is_error = _request("GET", f"/shells/{shell_id}/session-start", timeout=15)
    if is_error:
        return {"error": text}
    try:
        return json.loads(text)
    except Exception as e:
        return {"error": f"bad session-start payload: {e}"}


def execute_tool(name: str, params: dict):
    """Run one api_* tool call against the dos-arch API. Returns (text, is_error)."""
    method = METHOD_MAP.get(name)
    if not method:
        return f"unknown tool: {name}", True
    path = params.get("path")
    if not isinstance(path, str) or not path:
        return "missing or invalid path", True
    body = params.get("body")
    # Process-wide cap on concurrent tool calls — protects our own API.
    with TOOL_SEMAPHORE:
        return _request(method, path, body=body, timeout=30)


def post_reply(shell_id: int, body: str, source_message_id, session_id, user_id, tokens: int):
    text, is_error = _request("POST", f"/shells/{shell_id}/chat/reply", body={
        "body": body,
        "source_message_id": source_message_id,
        "session_id": session_id,
        "user_id": user_id,
        "tokens": tokens,
        "is_new_session": False,
    })
    return (0 if is_error else 200), text


# ── Context assembly ──────────────────────────────────────────────────────────

def render_dynamic(dyn: dict) -> str:
    """Block 3 — the live tail returned by /session-start, as a text block."""
    lines = [
        "## LIVE STATE (this turn — not cached)",
        "",
        f"- Current time (UTC): {dyn.get('datetime_utc', '?')}",
        f"- Open flags: {dyn.get('flags_open', 0)}",
    ]
    msgs = dyn.get("unread_messages") or []
    if msgs:
        lines.append(f"- Unread shell messages: {len(msgs)}")
        for m in msgs:
            lines.append(f"    - from shell {m.get('sender_id')}: {m.get('subject') or '(no subject)'}")
    else:
        lines.append("- Unread shell messages: none")
    return "\n".join(lines)


def serialize_assistant(content_blocks) -> list[dict]:
    out = []
    for b in content_blocks:
        if b.type == "text":
            out.append({"type": "text", "text": b.text})
        elif b.type == "tool_use":
            out.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
    return out


# ── The agent loop ────────────────────────────────────────────────────────────

def process_inbound(client: anthropic.Anthropic, con: sqlite3.Connection, shell, msg) -> None:
    window  = load_user_history_window(con, msg["user_id"])
    history = load_history(con, msg["chat_session_id"], window)
    if not history:
        history = [{"role": "user", "content": msg["body"]}]
    messages = [{"role": m["role"], "content": m["content"]} for m in history]

    ss = fetch_session_start(shell["shell_id"])
    if "error" in ss:
        print(f"[{shell['display_name']}] session-start failed: {ss['error']}",
              file=sys.stderr, flush=True)
        post_reply(shell["shell_id"], "(I could not load my context — please retry.)",
                   msg["message_id"], msg["chat_session_id"], msg["user_id"], 0)
        return

    # Block 1-2 (materialized boot document) caches; Block 3 (live tail) does not.
    system_blocks = [
        {"type": "text", "text": ss["boot_document"], "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": render_dynamic(ss.get("dynamic", {}))},
    ]

    total_tokens = 0
    final_text   = ""

    try:
        for iteration in range(MAX_TOOL_ITER):
            response = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=system_blocks,
                tools=TOOLS,
                messages=messages,
            )
            u = response.usage
            total_tokens += (u.input_tokens or 0) + (u.output_tokens or 0)
            print(f"[{shell['display_name']}] iter={iteration} stop={response.stop_reason} "
                  f"in={u.input_tokens} out={u.output_tokens}", flush=True)

            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": serialize_assistant(response.content)})
                tool_results = []
                for b in response.content:
                    if b.type != "tool_use":
                        continue
                    result, is_error = execute_tool(b.name, b.input)
                    short_in  = json.dumps(b.input)[:140].replace("\n", " ")
                    short_out = result[:140].replace("\n", " ")
                    print(f"  tool={b.name} in={short_in} err={is_error} out={short_out}", flush=True)
                    tr = {"type": "tool_result", "tool_use_id": b.id, "content": result}
                    if is_error:
                        tr["is_error"] = True
                    tool_results.append(tr)
                messages.append({"role": "user", "content": tool_results})
                continue

            # end_turn / stop_sequence / max_tokens — capture final text.
            final_text = "\n".join(b.text for b in response.content if b.type == "text").strip()
            break
        else:
            print(f"  hit MAX_TOOL_ITER={MAX_TOOL_ITER} without end_turn", flush=True)
            final_text = final_text or "(tool loop exceeded — no final reply)"
    except anthropic.APIError as e:
        # SDK retries (max_retries=5) already exhausted.
        print(f"  Anthropic API error after retries: {type(e).__name__}: {e}",
              file=sys.stderr, flush=True)
        final_text = "(I'm currently overloaded — please retry in a moment.)"

    if not final_text:
        final_text = "(empty reply)"

    status, resp_body = post_reply(
        shell["shell_id"], final_text, msg["message_id"],
        msg["chat_session_id"], msg["user_id"], total_tokens,
    )
    print(f"[{shell['display_name']}] reply_status={status} tokens={total_tokens}", flush=True)
    if status >= 400:
        # Persistent post_reply failure — raise so the caller marks the source
        # read and we don't infinite-loop the same expensive turn.
        print(f"  reply error body: {resp_body}", file=sys.stderr, flush=True)
        raise RuntimeError(f"post_reply failed status={status}")


# ── Concurrency: thread per shell, pool per shell, lock per session ───────────-

def _run_turn(client, shell, msg, in_flight, in_flight_started, in_flight_warned, lock):
    """Pool worker: process one message for one session. Opens its own DB
    connection. Releases the session from in_flight only AFTER the source is
    marked read — otherwise the parent thread could re-pick the same row."""
    sid = msg["chat_session_id"]
    shell_id = shell["shell_id"]
    try:
        con = db()
        try:
            con.execute(
                "UPDATE chat_sessions SET turn_in_flight_at=CURRENT_TIMESTAMP, "
                "turn_in_flight_message_id=? WHERE chat_session_id=?",
                (msg["message_id"], sid),
            )
            con.commit()
            try:
                process_inbound(client, con, shell, msg)
            except Exception as e:
                print(f"ERROR shell={shell_id} msg={msg['message_id']}: {e}",
                      file=sys.stderr, flush=True)
                traceback.print_exc()
                con.execute(
                    "UPDATE chat_messages SET read_by_shell=1 WHERE message_id=?",
                    (msg["message_id"],),
                )
                con.commit()
            finally:
                con.execute(
                    "UPDATE chat_sessions SET turn_in_flight_at=NULL, "
                    "turn_in_flight_message_id=NULL WHERE chat_session_id=?",
                    (sid,),
                )
                con.commit()
        finally:
            con.close()
    finally:
        with lock:
            in_flight.discard(sid)
            in_flight_started.pop(sid, None)
            in_flight_warned.discard(sid)


def shell_loop(shell_id: int):
    """One thread per browser shell. Submits per-message work to a per-shell
    pool, with a per-session lock so two messages in the same session
    serialize (history dependency) while different sessions run in parallel.

    A sessionless inbound message (chat_session_id IS NULL) keys on None;
    such messages serialize against each other but that is acceptable —
    sessionless chat is the test/edge path, not the product path."""
    client = anthropic.Anthropic(max_retries=5)
    pool = concurrent.futures.ThreadPoolExecutor(
        max_workers=POOL_WORKERS, thread_name_prefix=f"shell-{shell_id}-w",
    )
    in_flight: set = set()
    in_flight_started: dict = {}
    in_flight_warned: set = set()
    lock = threading.Lock()

    while True:
        try:
            con = db()
            shell = load_shell(con, shell_id)
            if not shell:
                con.close()
                time.sleep(5.0)
                continue
            unread = fetch_unread_for_shell(con, shell_id)
            con.close()

            now = time.time()
            with lock:
                for sid, t0 in list(in_flight_started.items()):
                    if now - t0 > STUCK_SESSION_SEC and sid not in in_flight_warned:
                        print(f"WARN shell={shell_id} session={sid} in_flight for "
                              f"{int(now - t0)}s — possibly stuck", file=sys.stderr, flush=True)
                        in_flight_warned.add(sid)

            # Pick the oldest unread per session, skipping sessions in flight.
            with lock:
                snapshot = set(in_flight)
            picked = {}
            for msg in unread:
                sid = msg["chat_session_id"]
                if sid in snapshot or sid in picked:
                    continue
                picked[sid] = msg

            with lock:
                for sid, msg in picked.items():
                    if sid in in_flight:
                        continue
                    in_flight.add(sid)
                    in_flight_started[sid] = time.time()
                    pool.submit(_run_turn, client, shell, msg,
                                in_flight, in_flight_started, in_flight_warned, lock)
        except Exception as e:
            print(f"shell-{shell_id} loop error: {e}", file=sys.stderr, flush=True)
            traceback.print_exc()
        time.sleep(POLL_MS / 1000.0)


def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    # Process-level exclusive lock — abort if another dispatch_live is running.
    # Two dispatchers would race on unread rows: same message twice, duplicate
    # Anthropic spend, garbled history.
    lockfile = open(LOCKFILE_PATH, "w")
    try:
        fcntl.flock(lockfile.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(f"ERROR: another dispatch_live holds {LOCKFILE_PATH} — aborting",
              file=sys.stderr, flush=True)
        sys.exit(1)
    lockfile.write(f"{os.getpid()}\n")
    lockfile.flush()

    # Boot-clear stale in-flight markers (safe — we are the sole dispatcher).
    # Assert WAL so concurrent workers writing chat_* never block readers.
    boot_con = db()
    journal_mode = boot_con.execute("PRAGMA journal_mode").fetchone()[0]
    if journal_mode.lower() != "wal":
        boot_con.execute("PRAGMA journal_mode=WAL")
        journal_mode = boot_con.execute("PRAGMA journal_mode").fetchone()[0]
    shell_ids = discover_browser_shell_ids(boot_con)
    if shell_ids:
        placeholders = ",".join("?" * len(shell_ids))
        boot_con.execute(
            f"UPDATE chat_sessions SET turn_in_flight_at=NULL, turn_in_flight_message_id=NULL "
            f"WHERE shell_id IN ({placeholders})", shell_ids,
        )
        boot_con.commit()
    boot_con.close()

    def _on_sigterm(signum, frame):
        print("dispatch_live SIGTERM — flushing in-flight markers", flush=True)
        try:
            con = db()
            if shell_ids:
                ph = ",".join("?" * len(shell_ids))
                con.execute(
                    f"UPDATE chat_sessions SET turn_in_flight_at=NULL, "
                    f"turn_in_flight_message_id=NULL WHERE shell_id IN ({ph})", shell_ids,
                )
                con.commit()
            con.close()
        except Exception as e:
            print(f"  flush failed: {e}", file=sys.stderr, flush=True)
        try:
            fcntl.flock(lockfile.fileno(), fcntl.LOCK_UN)
            lockfile.close()
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGTERM, _on_sigterm)
    signal.signal(signal.SIGINT, _on_sigterm)

    print(f"dispatch_live started — model={MODEL} api={API_BASE} "
          f"browser_shells={shell_ids} poll={POLL_MS}ms pool={POOL_WORKERS} "
          f"journal={journal_mode} pid={os.getpid()}", flush=True)

    if not shell_ids:
        print("  no shells with browser_chat=1 — idle. Set the flag and restart.", flush=True)

    threads = []
    for sid in shell_ids:
        t = threading.Thread(target=shell_loop, args=(sid,), name=f"shell-{sid}", daemon=True)
        t.start()
        threads.append(t)

    # Block forever; threads are daemons so SIGTERM kills the process cleanly.
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
