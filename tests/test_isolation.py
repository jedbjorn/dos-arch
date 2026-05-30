"""Tenant data-isolation acceptance suite (CC-108).

Encodes the spec invariant (`docs/specs/data-isolation.md`): authenticated as
Bob, no path reaches Alice's private rows — and the dual, that Alice and the
shell-self caller still reach their own. Each user-private surface here returned
**200 to an unauthenticated caller before the gate** — these assertions go red
without the predicate.

Identities (see conftest): Alice owns shell 101 / project 500; Bob owns shell
102 / project 501; shell 100 is a shared system shell. `shell_a` / `shell_b`
call with the shell's own api-key (the dispatcher's identity).
"""
import pytest

A = 101   # Alice's shell
SHARED = 100

# (label, path) — user-private reads on Alice's shell. Owner + shell-self may
# read; every other identity gets 404 (never 403).
PRIVATE_READS = [
    ("identity",      f"/shells/{A}/identity-entries"),
    ("decisions",     f"/shells/{A}/decisions"),
    ("archives",      f"/shells/{A}/archives"),
    ("archive-by-sess", f"/shells/{A}/archives/sess{A}"),
    ("chat",          f"/shells/{A}/chat"),
    ("chat-session",  f"/shells/{A}/chat/session"),
]


@pytest.mark.parametrize("label,path", PRIVATE_READS, ids=[p[0] for p in PRIVATE_READS])
def test_private_read_owner_and_self_allowed(label, path, alice, shell_a):
    assert alice.get(path).status_code == 200, f"owner blocked on {label}"
    assert shell_a.get(path).status_code == 200, f"shell-self blocked on {label}"


@pytest.mark.parametrize("label,path", PRIVATE_READS, ids=[p[0] for p in PRIVATE_READS])
def test_private_read_cross_tenant_denied(label, path, bob, anon, shell_b):
    assert bob.get(path).status_code == 404, f"cross-user LEAK on {label}"
    assert anon.get(path).status_code == 404, f"unauthenticated LEAK on {label}"
    assert shell_b.get(path).status_code == 404, f"cross-shell LEAK on {label}"


def test_archive_by_id_isolation(alice, bob, anon, ids):
    """Archives addressed by archive_id resolve to the owning shell first."""
    a_arch = f"/shell-memory-archives/{ids['archive_a']}"
    assert alice.get(a_arch).status_code == 200
    assert bob.get(a_arch).status_code == 404      # Bob cannot read Alice's archive
    assert anon.get(a_arch).status_code == 404


def test_get_shell_card_owner_sees_private(alice):
    r = alice.get(f"/shells/{A}")
    assert r.status_code == 200
    assert r.json()["current_state"] == "alice-private-state"


def test_get_shell_cross_tenant_denied(bob, anon):
    assert bob.get(f"/shells/{A}").status_code == 404
    assert anon.get(f"/shells/{A}").status_code == 404


def test_shared_shell_card_is_global_but_private_nulled(anon, bob, shell_a):
    """A shared shell's card is the Global class — visible to any authenticated
    caller (and anon) — but its private columns are nulled for non-owners."""
    for caller in (anon, bob, shell_a):
        r = caller.get(f"/shells/{SHARED}")
        assert r.status_code == 200, "shared card should be globally visible"
        body = r.json()
        assert body["display_name"] == "SharedSys"          # card visible
        assert body["current_state"] is None                # private nulled
        assert body["connections"] is None


# ── Mutations ────────────────────────────────────────────────────────────────

def test_mutate_current_state_isolation(alice, bob, anon):
    body = {"current_state": "changed-by-test"}
    assert alice.patch(f"/shells/{A}", json=body).status_code == 200
    assert bob.patch(f"/shells/{A}", json=body).status_code == 404
    assert anon.patch(f"/shells/{A}", json=body).status_code == 404


def test_create_decision_isolation(alice, shell_a, bob, shell_b, anon):
    body = {"decision": "x", "priority": "M"}
    assert alice.post(f"/shells/{A}/decisions", json=body).status_code == 200
    assert shell_a.post(f"/shells/{A}/decisions", json=body).status_code == 200
    assert bob.post(f"/shells/{A}/decisions", json=body).status_code == 404
    assert shell_b.post(f"/shells/{A}/decisions", json=body).status_code == 404
    assert anon.post(f"/shells/{A}/decisions", json=body).status_code == 404


# ── Inter-shell messages (shell-messages) ────────────────────────────────────

def test_shell_message_inbox_read_isolation(alice, shell_a, bob, anon, shell_b):
    """A shell's inbox (recipient_id=Alice's shell) is readable only by its
    owner / the shell itself / admin — not another tenant."""
    path = f"/shell-messages?recipient_id={A}"
    assert alice.get(path).status_code == 200
    assert shell_a.get(path).status_code == 200
    assert bob.get(path).status_code == 404
    assert anon.get(path).status_code == 404
    assert shell_b.get(path).status_code == 404


def test_shell_message_send_no_impersonation(alice, bob, shell_b):
    """You may send only *as* a shell you own — Bob cannot send as Alice's shell."""
    body = {"sender_id": A, "recipient_id": 102, "body": "x", "auto_prompt": False}
    assert alice.post("/shell-messages", json=body).status_code == 200
    assert bob.post("/shell-messages", json=body).status_code == 404
    assert shell_b.post("/shell-messages", json=body).status_code == 404


def test_shell_message_mark_read_isolation(alice, bob, ids):
    mid = ids["msg_to_a"]
    assert bob.patch(f"/shell-messages/{mid}").status_code == 404
    assert alice.patch(f"/shell-messages/{mid}").status_code == 200


# ── Broker secrets (keys.py) — admin only ────────────────────────────────────

def test_keys_admin_only(admin, bob, anon, shell_a):
    assert bob.get("/keys").status_code == 403
    assert anon.get("/keys").status_code == 403
    assert shell_a.get("/keys").status_code == 403          # non-admin shell
    # Admin passes the gate; the broker is unconfigured in tests → 503, not 403.
    assert admin.get("/keys").status_code != 403


# ── Flags — the already-built reference layer ────────────────────────────────

def test_flag_visibility(alice, bob, ids):
    """Alice (project owner) sees her team + private flags; Bob (not a member of
    project 500) sees neither — 404 on direct fetch."""
    team, priv = ids["flag_team"], ids["flag_priv"]
    assert alice.get(f"/flags/{team}").status_code == 200
    assert alice.get(f"/flags/{priv}").status_code == 200
    assert bob.get(f"/flags/{team}").status_code == 404
    assert bob.get(f"/flags/{priv}").status_code == 404


def test_flag_list_excludes_other_tenant(bob):
    r = bob.get("/flags")
    assert r.status_code == 200
    rows = r.json()
    rows = rows if isinstance(rows, list) else rows.get("flags", [])
    assert all(row.get("project_id") != 500 for row in rows), "Bob saw Alice's project flags"


def test_flags_project_id_not_null_constraint():
    """Migration 064 made flags.project_id physically NOT NULL — a flag can never
    be project-less (unscoped, invisible). Asserts the constraint reached the
    harness build (schema.sql + post-059 migrations)."""
    import os
    import sqlite3
    con = sqlite3.connect(os.environ["SHELL_DB_PATH"])
    try:
        cols = {r[1]: r for r in con.execute("PRAGMA table_info(flags)")}
        # PRAGMA table_info columns: (cid, name, type, notnull, dflt_value, pk)
        assert cols["project_id"][3] == 1, "flags.project_id must be NOT NULL (064)"
    finally:
        con.close()
