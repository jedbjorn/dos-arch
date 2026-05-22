#!/usr/bin/env python3
"""dispatch_live.py — the browser-chat dispatcher.

Ported from ExpLive (designs_os). Polls `chat_messages` for unread inbound
rows, runs a multi-turn tool loop against the model, and posts the final
assistant text via `POST /shells/{id}/chat/reply`.

dos-arch (CC-47 port, CC-49 adapter seam, CC-50 registry wiring; decision #108):
  - Provider-agnostic loop — every model call goes through a `ProviderAdapter`
    (agnostic-runtime §3.4, see `providers/`); this module names no provider.
  - Model is resolved per turn from the `models` registry: a conversation's
    `chat_sessions.model_id` selects the model and provider; an unset session
    falls back to the `DISPATCH_MODEL` default. The provider's adapter follows.
  - Tools are loaded per shell from `tools` / `shell_tools` (the join is the
    shell's tool set), not a hard-coded list.
  - No auth — dos-arch's API is open on localhost in alpha; the `X-API-Key`
    machinery is not ported. Required before any off-localhost exposure (CC-55).
  - Tokens only, no cost — `chat_messages.tokens` carries the per-turn total;
    cost varies per provider and is meaningless for local models.
  - Context is the materialized boot document: one per-session `session-start`
    call returns `{boot_document, dynamic}` — Block 1-2 cached, Block 3 live.

A shell joins the dispatcher by setting `shells.browser_chat = 1` and leaves
by clearing it. A supervisor loop re-checks membership every RECONCILE_SEC,
so a browser_chat change (e.g. the UI's shell-switch) takes effect without
a dispatcher restart.

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

# `providers/` is a sibling package; the script's own directory is on
# sys.path[0], so the bare import resolves when run as `python3 dispatch_live.py`.
from providers import (
    ProviderAdapter,
    ProviderError,
    assistant_message,
    get_adapter,
    tool_result_message,
)

# ── Config ────────────────────────────────────────────────────────────────────

_REPO = Path(__file__).resolve().parents[2]
DB_PATH       = os.environ.get("DISPATCH_DB_PATH", str(_REPO / "shell_core" / "shell_db.db"))
API_BASE      = os.environ.get("DISPATCH_API_BASE", "http://127.0.0.1:8001").rstrip("/")
MODEL         = os.environ.get("DISPATCH_MODEL", "claude-sonnet-4-6")  # fallback default
LOCKFILE_PATH = str(Path(__file__).resolve().parent / ".dispatch_live.lock")

POLL_MS                = 250
MAX_TOKENS             = 16384
MAX_TOOL_ITER          = 20
DEFAULT_HISTORY_WINDOW = 25          # fallback if users.chat_history_window unset
POOL_WORKERS           = int(os.environ.get("DISPATCH_POOL_WORKERS", "5"))
TOOL_CONCURRENCY       = int(os.environ.get("DISPATCH_TOOL_CONCURRENCY", "20"))
STUCK_SESSION_SEC      = 300         # warn if a session is in-flight this long
RECONCILE_SEC          = 5           # supervisor: re-check browser_chat membership

# Process-wide cap on in-flight API calls from execute_tool — N workers × 20
# tool iterations could otherwise saturate our own API.
TOOL_SEMAPHORE = threading.Semaphore(TOOL_CONCURRENCY)

# The api_* tools are data now — loaded per shell from `tools` / `shell_tools`
# (see load_tools). METHOD_MAP stays: it is the executor's name->verb mapping,
# which is dispatcher-side, not part of a tool's stored definition.
METHOD_MAP = {"api_get": "GET", "api_post": "POST", "api_patch": "PATCH", "api_delete": "DELETE"}

# One cached adapter per (provider, endpoint) — adapters are thread-safe and
# reused across shell threads. Built lazily. Endpoint matters for `local`
# (Ollama can be served from many hosts); for cloud providers it is None.
_ADAPTERS: dict[tuple[str, str | None], ProviderAdapter] = {}
_ADAPTERS_LOCK = threading.Lock()


def adapter_for(provider: str, endpoint: str | None = None) -> ProviderAdapter:
    key = (provider, endpoint)
    with _ADAPTERS_LOCK:
        a = _ADAPTERS.get(key)
        if a is None:
            a = get_adapter(provider, endpoint=endpoint)
            _ADAPTERS[key] = a
        return a


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


def clear_in_flight(con: sqlite3.Connection, shell_ids) -> None:
    """Reset stale turn-in-flight markers for these shells' chat sessions.
    Safe because dispatch_live holds an exclusive process lock — it is the
    sole writer of these markers. Called per shell as it joins the
    dispatcher, so a shell carrying markers from a past run starts clean."""
    ids = list(shell_ids)
    if not ids:
        return
    ph = ",".join("?" * len(ids))
    con.execute(
        f"UPDATE chat_sessions SET turn_in_flight_at=NULL, "
        f"turn_in_flight_message_id=NULL WHERE shell_id IN ({ph})", ids,
    )
    con.commit()


def load_shell(con: sqlite3.Connection, shell_id: int):
    return con.execute(
        "SELECT shell_id, display_name FROM shells WHERE shell_id=?", (shell_id,)
    ).fetchone()


def resolve_model(con: sqlite3.Connection, chat_session_id) -> tuple[str, str, str | None]:
    """(model_name, provider, endpoint) for this turn. A session-pinned model
    (chat_sessions.model_id) wins; otherwise the DISPATCH_MODEL default,
    resolved through the registry. `endpoint` is the per-model host (NULL
    for cloud providers using the SDK default; set for local Ollama). If
    the default is not registered, the provider is assumed to be Anthropic."""
    if chat_session_id:
        row = con.execute(
            "SELECT m.name AS name, m.provider AS provider, m.endpoint AS endpoint "
            "FROM chat_sessions cs JOIN models m ON m.model_id = cs.model_id "
            "WHERE cs.chat_session_id=?",
            (chat_session_id,),
        ).fetchone()
        if row:
            return row["name"], row["provider"], row["endpoint"]
    row = con.execute(
        "SELECT name, provider, endpoint FROM models WHERE name=?", (MODEL,)
    ).fetchone()
    if row:
        return row["name"], row["provider"], row["endpoint"]
    return MODEL, "anthropic", None


def load_tools(con: sqlite3.Connection, shell_id: int) -> list[dict]:
    """The shell's tool set — the `tools` x `shell_tools` join, active only —
    as normalized tool dicts {name, description, spec}. `spec` is the parsed
    JSON-Schema parameter object; each adapter projects it onto its dialect."""
    rows = con.execute(
        "SELECT t.name AS name, t.description AS description, t.spec AS spec "
        "FROM tools t JOIN shell_tools st ON st.tool_id = t.tool_id "
        "WHERE st.shell_id=? AND t.status='active' ORDER BY t.tool_id",
        (shell_id,),
    ).fetchall()
    return [
        {
            "name": r["name"],
            "description": r["description"],
            "spec": json.loads(r["spec"]) if r["spec"] else {},
        }
        for r in rows
    ]


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


def fetch_session_start(shell_id: int, chat_session_id) -> dict:
    """GET the materialized boot document + live dynamic tail for a chat
    session. Returns the decoded payload, or {'error': ...} if the call fails
    or the inbound message carries no session."""
    if not chat_session_id:
        return {"error": "message has no chat session"}
    text, is_error = _request(
        "GET", f"/shells/{shell_id}/sessions/{chat_session_id}/session-start",
        timeout=15)
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


# ── The agent loop ────────────────────────────────────────────────────────────

def process_inbound(con: sqlite3.Connection, shell, msg) -> None:
    window  = load_user_history_window(con, msg["user_id"])
    history = load_history(con, msg["chat_session_id"], window)
    if not history:
        history = [{"role": "user", "content": msg["body"]}]
    messages = [{"role": m["role"], "content": m["content"]} for m in history]

    # Stacked inbound: if this message's session history already ends with an
    # assistant turn, a reply landed after it — it was answered together with
    # an earlier message in the same session (the model sees the whole window).
    # Mark it read and skip; re-answering would hand the model a conversation
    # ending on its own turn, which providers reject (e.g. Anthropic 400,
    # "conversation must end with a user message").
    if messages and messages[-1]["role"] == "assistant":
        con.execute("UPDATE chat_messages SET read_by_shell=1 WHERE message_id=?",
                    (msg["message_id"],))
        con.commit()
        print(f"[{shell['display_name']}] msg={msg['message_id']} already covered "
              f"by a later reply — skipping", flush=True)
        return

    # Resolve the model + provider for this conversation, then the adapter and
    # the shell's tool set. Anything provider-specific is now behind `adapter`.
    model_name, provider, endpoint = resolve_model(con, msg["chat_session_id"])
    adapter = adapter_for(provider, endpoint)
    tools   = load_tools(con, shell["shell_id"])
    # Every provider — including local — gets the api_* tool surface. Tool
    # support varies model to model (gemma handles it, deepseek-r1 hard-400s
    # on tools); per-model capability gating lands with the tools/prompts pass.
    ep = f" endpoint={endpoint}" if endpoint else ""
    print(f"[{shell['display_name']}] msg={msg['message_id']} model={model_name} "
          f"provider={provider}{ep} tools={len(tools)}", flush=True)

    ss = fetch_session_start(shell["shell_id"], msg["chat_session_id"])
    if "error" in ss:
        print(f"[{shell['display_name']}] session-start failed: {ss['error']}",
              file=sys.stderr, flush=True)
        post_reply(shell["shell_id"], "(I could not load my context — please retry.)",
                   msg["message_id"], msg["chat_session_id"], msg["user_id"], 0)
        return

    # Normalized system blocks: Block 1-2 (materialized boot document) is
    # cacheable; Block 3 (the live tail) is not. The adapter projects `cache`.
    system_blocks = [
        {"text": ss["boot_document"], "cache": True},
        {"text": render_dynamic(ss.get("dynamic", {})), "cache": False},
    ]

    total_tokens = 0
    final_text   = ""

    try:
        for iteration in range(MAX_TOOL_ITER):
            request  = adapter.format_request(system_blocks, tools, messages, model_name, MAX_TOKENS)
            response = adapter.call(request)
            parsed   = adapter.parse_response(response)
            u = parsed.usage
            total_tokens += (u.get("input_tokens") or 0) + (u.get("output_tokens") or 0)
            print(f"[{shell['display_name']}] iter={iteration} stop={parsed.stop_reason} "
                  f"in={u.get('input_tokens')} out={u.get('output_tokens')}", flush=True)

            if parsed.stop_reason == "tool_use":
                messages.append(assistant_message(parsed))
                tool_results = []
                for tc in parsed.tool_calls:
                    result, is_error = execute_tool(tc["name"], tc["input"])
                    short_in  = json.dumps(tc["input"])[:140].replace("\n", " ")
                    short_out = result[:140].replace("\n", " ")
                    print(f"  tool={tc['name']} in={short_in} err={is_error} out={short_out}", flush=True)
                    tool_results.append({"id": tc["id"], "content": result, "is_error": is_error})
                messages.append(tool_result_message(tool_results))
                continue

            # end_turn / stop_sequence / max_tokens — capture final text.
            final_text = parsed.text
            break
        else:
            print(f"  hit MAX_TOOL_ITER={MAX_TOOL_ITER} without end_turn", flush=True)
            final_text = final_text or "(tool loop exceeded — no final reply)"
    except ProviderError as e:
        # Adapter retries already exhausted.
        print(f"  provider API error after retries: {e}", file=sys.stderr, flush=True)
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

def _run_turn(shell, msg, in_flight, in_flight_started, in_flight_warned, lock):
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
                process_inbound(con, shell, msg)
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


def shell_loop(shell_id: int, stop_event: threading.Event):
    """One thread per browser shell. Submits per-message work to a per-shell
    pool, with a per-session lock so two messages in the same session
    serialize (history dependency) while different sessions run in parallel.

    Runs until `stop_event` is set — the supervisor sets it when the shell
    drops browser_chat=1. On stop the polling halts at once and the pool
    drains in-flight turns before the thread exits; the supervisor will not
    re-spawn a thread for this shell until the old one is gone, so a shell
    never has two loops racing the same unread rows.

    A sessionless inbound message (chat_session_id IS NULL) keys on None;
    such messages serialize against each other but that is acceptable —
    sessionless chat is the test/edge path, not the product path."""
    # The adapter is resolved per turn inside process_inbound (model -> provider
    # -> adapter_for), so the shell thread holds no provider state.
    pool = concurrent.futures.ThreadPoolExecutor(
        max_workers=POOL_WORKERS, thread_name_prefix=f"shell-{shell_id}-w",
    )
    in_flight: set = set()
    in_flight_started: dict = {}
    in_flight_warned: set = set()
    lock = threading.Lock()

    while not stop_event.is_set():
        try:
            con = db()
            shell = load_shell(con, shell_id)
            if not shell:
                con.close()
                stop_event.wait(5.0)
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
                    pool.submit(_run_turn, shell, msg,
                                in_flight, in_flight_started, in_flight_warned, lock)
        except Exception as e:
            print(f"shell-{shell_id} loop error: {e}", file=sys.stderr, flush=True)
            traceback.print_exc()
        stop_event.wait(POLL_MS / 1000.0)

    pool.shutdown(wait=True)
    print(f"shell-{shell_id} loop stopped — browser_chat cleared", flush=True)


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

    # Assert WAL so concurrent workers writing chat_* never block readers.
    boot_con = db()
    journal_mode = boot_con.execute("PRAGMA journal_mode").fetchone()[0]
    if journal_mode.lower() != "wal":
        boot_con.execute("PRAGMA journal_mode=WAL")
        journal_mode = boot_con.execute("PRAGMA journal_mode").fetchone()[0]
    boot_con.close()

    # Live shell membership. `running` holds one thread + stop-event per
    # browser_chat=1 shell; `draining` holds threads told to stop that have
    # not yet finished their in-flight turns. The supervisor loop reconciles
    # `running` against the DB every RECONCILE_SEC. Per-shell in-flight
    # markers are cleared as each shell joins (clear_in_flight).
    running: dict[int, tuple[threading.Thread, threading.Event]] = {}
    draining: list[tuple[int, threading.Thread]] = []

    def _on_sigterm(signum, frame):
        print("dispatch_live SIGTERM — stopping shell loops + flushing markers", flush=True)
        for _t, ev in running.values():
            ev.set()
        try:
            con = db()
            clear_in_flight(con, list(running.keys()))
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

    print(f"dispatch_live started — model={MODEL} api={API_BASE} poll={POLL_MS}ms "
          f"reconcile={RECONCILE_SEC}s pool={POOL_WORKERS} journal={journal_mode} "
          f"pid={os.getpid()}", flush=True)

    # Supervisor: spawn a shell_loop for every shell that gains browser_chat=1,
    # stop the loop for every shell that loses it. A re-activated shell waits
    # until its previous (draining) thread is gone, so its unread rows are
    # never polled by two loops at once.
    while True:
        try:
            draining = [(sid, t) for sid, t in draining if t.is_alive()]
            draining_shells = {sid for sid, _ in draining}

            con = db()
            current = set(discover_browser_shell_ids(con))

            for sid in sorted(running.keys() - current):
                t, ev = running.pop(sid)
                ev.set()
                draining.append((sid, t))
                print(f"  - shell {sid} left dispatcher (browser_chat=0)", flush=True)

            for sid in sorted(current - running.keys()):
                if sid in draining_shells:
                    continue   # prior thread still draining — retry next cycle
                clear_in_flight(con, [sid])
                ev = threading.Event()
                t = threading.Thread(target=shell_loop, args=(sid, ev),
                                     name=f"shell-{sid}", daemon=True)
                t.start()
                running[sid] = (t, ev)
                print(f"  + shell {sid} joined dispatcher (browser_chat=1)", flush=True)

            con.close()
        except Exception as e:
            print(f"supervisor loop error: {e}", file=sys.stderr, flush=True)
            traceback.print_exc()
        time.sleep(RECONCILE_SEC)


if __name__ == "__main__":
    main()
