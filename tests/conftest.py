"""Isolation-suite fixtures — the executable acceptance gate for
`docs/specs/data-isolation.md` (CC-108).

A throwaway DB is built from `schema.sql` + the post-059 migrations and seeded
with **two tenants** (Alice / Bob), a shared system shell, and one private
mind + one project per tenant. Tests then assert the spec's invariant: as Bob,
no path reaches Alice's private rows (404), and vice-versa, while each tenant
reaches its own (200) and shared/global surfaces stay visible.

The DB path is injected via `SHELL_DB_PATH` **before** importing the app — the
auth middleware opens `db()` directly, so a `Depends` override alone would miss
it. The TestClient is created without a `with` block on purpose: that skips the
app's startup hooks (catalogue / model sync) which would hit the network.
"""
import hashlib
import os
import pathlib
import sqlite3
import sys
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SHELL_CORE = ROOT / "shell_core"
sys.path.insert(0, str(SHELL_CORE))

# ── Point the app at a throwaway DB + neutralize prod-only env ────────────────
_TMP = tempfile.NamedTemporaryFile(prefix="dosarch-iso-", suffix=".db", delete=False)
_TMP.close()
os.environ["SHELL_DB_PATH"] = _TMP.name
os.environ.setdefault("AUTH_COOKIE_SECURE", "")     # plain `dsess` cookie, no __Host-
os.environ.pop("INTERNAL_PROXY_SECRET", None)        # no proxy seam in tests
os.environ.pop("BROKER_BASE", None)                  # /keys admin path -> 503, never egress
os.environ.pop("BROKER_ADMIN_TOKEN", None)

SCHEMA = SHELL_CORE / "schema.sql"
MIGRATIONS = SHELL_CORE / "migrations"

# Identities, fixed so tests can address rows by literal id.
USER_A, USER_B, USER_ADMIN = 10, 20, 1
SHELL_SHARED, SHELL_A, SHELL_B = 100, 101, 102
PROJ_A, PROJ_B = 500, 501
KEY_SHARED, KEY_A, KEY_B = "SHAREDKEY", "ALICEKEY", "BOBKEY"
ALICE_STATE = "alice-private-state"

_IDS: dict[str, int] = {}   # captured rowids (flags) for tests


def _sha(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()


def _build_schema(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA.read_text())
    for m in sorted(MIGRATIONS.glob("*.sql")):
        if int(m.name[:3]) <= 59:
            continue  # already folded into schema.sql
        try:
            con.executescript(m.read_text())
        except sqlite3.OperationalError as e:
            # schema.sql is current through ~061; tolerate the columns/objects it
            # already carries. Re-raise anything that is not an idempotent replay.
            if "duplicate column" in str(e) or "already exists" in str(e):
                continue
            raise
    con.commit()


def _seed(con: sqlite3.Connection) -> None:
    con.execute("INSERT OR IGNORE INTO users (user_id, username, is_admin) VALUES (?,?,1)",
                (USER_ADMIN, "operator"))
    con.execute("INSERT INTO users (user_id, username, is_admin) VALUES (?,?,0)", (USER_A, "alice"))
    con.execute("INSERT INTO users (user_id, username, is_admin) VALUES (?,?,0)", (USER_B, "bob"))

    def shell(sid, uid, shared, name, short, key, state):
        con.execute(
            "INSERT INTO shells (shell_id, display_name, shortname, user_id, is_shared, "
            "is_admin, current_state, connections, api_key, api_key_hash) "
            "VALUES (?,?,?,?,?,0,?,?,?,?)",
            (sid, name, short, uid, shared, state, f"{short}-conn", key, _sha(key)))
    shell(SHELL_SHARED, None, 1, "SharedSys", "shared", KEY_SHARED, "shared-state")
    shell(SHELL_A, USER_A, 0, "AliceShell", "alice", KEY_A, ALICE_STATE)
    shell(SHELL_B, USER_B, 0, "BobShell", "bob", KEY_B, "bob-private-state")

    for pid, uid, short in ((PROJ_A, USER_A, "pa"), (PROJ_B, USER_B, "pb")):
        con.execute("INSERT INTO projects (project_id, shortname, title) VALUES (?,?,?)",
                    (pid, short, f"{short}-title"))
        con.execute("INSERT INTO user_projects (user_id, project_id, role) VALUES (?,?, 'owner')",
                    (uid, pid))

    for sid in (SHELL_A, SHELL_B):
        con.execute("INSERT INTO shell_identity_entries (shell_id, kind, body) VALUES (?, 'seed', ?)",
                    (sid, f"seed-{sid}"))
        con.execute("INSERT INTO shell_decisions (shell_id, decision_date, decision) "
                    "VALUES (?, date('now'), ?)", (sid, f"decision-{sid}"))
        cur = con.execute("INSERT INTO shell_memory_archives (shell_id, session_id, date, full_narrative) "
                          "VALUES (?, ?, date('now'), ?)", (sid, f"sess{sid}", f"narr-{sid}"))
        _IDS["archive_a" if sid == SHELL_A else "archive_b"] = cur.lastrowid
        uid = USER_A if sid == SHELL_A else USER_B
        con.execute("INSERT INTO chat_sessions (chat_session_id, shell_id, user_id, is_active) "
                    "VALUES (?,?,?,1)", (f"cs{sid}", sid, uid))
        con.execute("INSERT INTO chat_messages (shell_id, direction, user_id, body, chat_session_id) "
                    "VALUES (?, 'inbound', ?, 'hi', ?)", (sid, uid, f"cs{sid}"))

    # An inter-shell message to Alice's shell (Bob must not read it).
    cur = con.execute(
        "INSERT INTO shell_messages (sender_id, recipient_id, subject, body) VALUES (?,?,?,?)",
        (SHELL_SHARED, SHELL_A, "hi", "secret-to-alice"))
    _IDS["msg_to_a"] = cur.lastrowid

    # Two flags in Alice's project: one team-visible, one creator-private.
    cur = con.execute(
        "INSERT INTO flags (display_name, priority, created_date, shell_id, project_id, "
        "created_by_user_id, team_flag) VALUES ('A-team','Medium',date('now'),?,?,?,1)",
        (SHELL_A, PROJ_A, USER_A))
    _IDS["flag_team"] = cur.lastrowid
    cur = con.execute(
        "INSERT INTO flags (display_name, priority, created_date, shell_id, project_id, "
        "created_by_user_id, team_flag) VALUES ('A-priv','Medium',date('now'),?,?,?,0)",
        (SHELL_A, PROJ_A, USER_A))
    _IDS["flag_priv"] = cur.lastrowid
    con.commit()


# Build + seed once at import (before the app is imported below).
_con = sqlite3.connect(_TMP.name)
_build_schema(_con)
_seed(_con)

from api.common.sessions import COOKIE_NAME, create_session  # noqa: E402

_TOKENS = {
    "alice": create_session(_con, USER_A, None),
    "bob":   create_session(_con, USER_B, None),
    "admin": create_session(_con, USER_ADMIN, None),
}
_con.close()

from api.main import app  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402


class Caller:
    """A request maker carrying a fixed identity (session cookie or shell key)."""
    def __init__(self, client, *, cookie=None, bearer=None):
        self._c = client
        self._headers = {}
        if cookie:
            self._headers["Cookie"] = f"{COOKIE_NAME}={cookie}"
        if bearer:
            self._headers["Authorization"] = f"Bearer {bearer}"

    def _do(self, method, path, **kw):
        headers = {**self._headers, **kw.pop("headers", {})}
        return self._c.request(method, path, headers=headers, **kw)

    def get(self, p, **kw):    return self._do("GET", p, **kw)
    def post(self, p, **kw):   return self._do("POST", p, **kw)
    def patch(self, p, **kw):  return self._do("PATCH", p, **kw)
    def delete(self, p, **kw): return self._do("DELETE", p, **kw)


@pytest.fixture(scope="session")
def _client():
    # No `with` block → app startup hooks (catalogue / model sync) do not fire.
    return TestClient(app)


@pytest.fixture
def alice(_client):  return Caller(_client, cookie=_TOKENS["alice"])
@pytest.fixture
def bob(_client):    return Caller(_client, cookie=_TOKENS["bob"])
@pytest.fixture
def admin(_client):  return Caller(_client, cookie=_TOKENS["admin"])
@pytest.fixture
def anon(_client):   return Caller(_client)
@pytest.fixture
def shell_a(_client): return Caller(_client, bearer=KEY_A)
@pytest.fixture
def shell_b(_client): return Caller(_client, bearer=KEY_B)


@pytest.fixture
def ids():
    return dict(_IDS)
