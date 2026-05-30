"""Domain-router isolation suite (CC-108) — contacts.

Project-team scoping: a contact is visible to a member of *any* project it is
filed under, and to nobody else. Reuses the two-tenant fixtures from conftest
(Alice owns project 500, Bob owns 501) and seeds its own contact rows directly
into the shared test DB (via SHELL_DB_PATH) so it never touches conftest.
"""
import os
import sqlite3

import pytest

PROJ_A, PROJ_B = 500, 501   # Alice's / Bob's projects (see conftest)


@pytest.fixture(scope="module")
def contacts():
    """Seed one Alice-only contact, one Bob-only, and one shared (filed under
    both projects). Returns their ids."""
    con = sqlite3.connect(os.environ["SHELL_DB_PATH"])
    try:
        ids = {}

        def mk(name, project_ids):
            cur = con.execute(
                "INSERT INTO contacts (name, default_project_id) VALUES (?, ?)",
                (name, project_ids[0]))
            cid = cur.lastrowid
            con.executemany(
                "INSERT INTO contact_projects (contact_id, project_id) VALUES (?, ?)",
                [(cid, p) for p in project_ids])
            return cid

        ids["alice"] = mk("AliceContact", [PROJ_A])
        ids["bob"] = mk("BobContact", [PROJ_B])
        ids["bob_keep"] = mk("BobKeep", [PROJ_B])   # never deleted — invisibility cases
        ids["shared"] = mk("SharedContact", [PROJ_A, PROJ_B])
        con.commit()
        return ids
    finally:
        con.close()


def test_get_contact_isolation(alice, bob, anon, contacts):
    c = contacts["alice"]
    assert alice.get(f"/contacts/{c}").status_code == 200
    assert bob.get(f"/contacts/{c}").status_code == 404      # not a member of project 500
    assert anon.get(f"/contacts/{c}").status_code == 404


def test_shared_contact_visible_to_both(alice, bob, contacts):
    """A contact filed under both projects (N:M) is visible to each member."""
    c = contacts["shared"]
    assert alice.get(f"/contacts/{c}").status_code == 200
    assert bob.get(f"/contacts/{c}").status_code == 200


def test_list_contacts_scoped(alice, bob, contacts):
    a_names = {r["name"] for r in alice.get("/contacts").json()["contacts"]}
    b_names = {r["name"] for r in bob.get("/contacts").json()["contacts"]}
    assert "AliceContact" in a_names and "SharedContact" in a_names
    assert "BobContact" not in a_names              # Alice can't see Bob-only
    assert "AliceContact" not in b_names            # and vice-versa
    assert "SharedContact" in b_names


def test_create_requires_membership(alice, bob, anon):
    body = {"name": "New", "project_ids": [PROJ_A]}
    assert alice.post("/contacts", json=body).status_code == 200       # Alice owns 500
    assert bob.post("/contacts", json=body).status_code == 404         # Bob is not a member
    assert anon.post("/contacts", json=body).status_code == 404


def test_create_cross_project_denied(alice):
    """Alice cannot file a contact under Bob's project."""
    assert alice.post("/contacts", json={"name": "X", "project_ids": [PROJ_B]}).status_code == 404


def test_create_requires_a_project(alice):
    assert alice.post("/contacts", json={"name": "X", "project_ids": []}).status_code == 422


def test_mutate_contact_isolation(alice, bob, anon, contacts):
    c = contacts["alice"]
    body = {"name": "Renamed"}
    assert bob.patch(f"/contacts/{c}", json=body).status_code == 404
    assert anon.patch(f"/contacts/{c}", json=body).status_code == 404
    assert alice.patch(f"/contacts/{c}", json=body).status_code == 200


def test_delete_contact_isolation(alice, bob, contacts):
    c = contacts["bob"]
    assert alice.delete(f"/contacts/{c}").status_code == 404     # Alice can't delete Bob's
    assert bob.delete(f"/contacts/{c}").status_code == 200


# ── Emails (file under one project — compartmentalization) ────────────────────

@pytest.fixture(scope="module")
def emails(contacts):
    """Two emails about the *shared* contact — one filed under Alice's project,
    one under Bob's. Each is visible only to that project's member, even though
    both can see the contact card."""
    con = sqlite3.connect(os.environ["SHELL_DB_PATH"])
    try:
        ids = {}
        for key, pid in (("alice", PROJ_A), ("bob", PROJ_B)):
            cur = con.execute(
                "INSERT INTO emails (contact_id, project_id, direction, subject) "
                "VALUES (?,?,?,?)", (contacts["shared"], pid, "inbound", f"to-{key}"))
            ids[key] = cur.lastrowid
        con.commit()
        return ids
    finally:
        con.close()


def test_email_read_isolation(alice, bob, anon, emails):
    e = emails["alice"]
    assert alice.get(f"/emails/{e}").status_code == 200
    assert bob.get(f"/emails/{e}").status_code == 404
    assert anon.get(f"/emails/{e}").status_code == 404


def test_email_compartmentalization(bob, contacts, emails):
    """Bob can see the shared contact's card (via project 501) but NOT an email
    filed under Alice's project (500) — the contact is broader than its mail."""
    assert bob.get(f"/contacts/{contacts['shared']}").status_code == 200   # card visible
    assert bob.get(f"/emails/{emails['alice']}").status_code == 404        # mail compartmented


def test_email_list_scoped(alice, bob, emails):
    a_subjects = {r["subject"] for r in alice.get("/emails").json()["emails"]}
    b_subjects = {r["subject"] for r in bob.get("/emails").json()["emails"]}
    assert "to-alice" in a_subjects and "to-alice" not in b_subjects
    assert "to-bob" in b_subjects and "to-bob" not in a_subjects


def test_email_create_requires_filing_membership(alice, bob, contacts):
    sc = contacts["shared"]
    # Alice files under her project (500); Bob cannot file under 500.
    assert alice.post("/emails", json={"contact_id": sc, "project_id": PROJ_A}).status_code == 200
    assert bob.post("/emails", json={"contact_id": sc, "project_id": PROJ_A}).status_code == 404
    # Alice cannot file under Bob's project (501) even for a contact she shares.
    assert alice.post("/emails", json={"contact_id": sc, "project_id": PROJ_B}).status_code == 404


def test_email_create_needs_visible_contact(alice, contacts):
    """Alice cannot record an email against Bob-only contact she can't see."""
    assert alice.post("/emails", json={"contact_id": contacts["bob_keep"],
                                       "project_id": PROJ_A}).status_code == 404


def test_email_refile_requires_membership(alice, emails):
    e = emails["alice"]
    assert alice.patch(f"/emails/{e}", json={"project_id": PROJ_B}).status_code == 404  # not a member
    assert alice.patch(f"/emails/{e}", json={"subject": "edited"}).status_code == 200


def test_email_delete_isolation(alice, bob, emails):
    e = emails["bob"]
    assert alice.delete(f"/emails/{e}").status_code == 404
    assert bob.delete(f"/emails/{e}").status_code == 200


# ── Events (N:M projects/contacts/users) ──────────────────────────────────────

@pytest.fixture(scope="module")
def events():
    """One event under Alice's project, one under Bob's."""
    con = sqlite3.connect(os.environ["SHELL_DB_PATH"])
    try:
        ids = {}
        for key, pid in (("alice", PROJ_A), ("bob", PROJ_B)):
            cur = con.execute("INSERT INTO events (title) VALUES (?)", (f"event-{key}",))
            eid = cur.lastrowid
            con.execute("INSERT INTO event_projects (event_id, project_id, is_primary) VALUES (?,?,1)",
                        (eid, pid))
            ids[key] = eid
        con.commit()
        return ids
    finally:
        con.close()


def test_event_read_isolation(alice, bob, anon, events):
    e = events["alice"]
    assert alice.get(f"/events/{e}").status_code == 200
    assert bob.get(f"/events/{e}").status_code == 404
    assert anon.get(f"/events/{e}").status_code == 404


def test_event_list_scoped(alice, bob, events):
    a = {r["title"] for r in alice.get("/events").json()["events"]}
    b = {r["title"] for r in bob.get("/events").json()["events"]}
    assert "event-alice" in a and "event-alice" not in b
    assert "event-bob" in b and "event-bob" not in a


def test_event_create_requires_membership(alice, bob):
    body = {"title": "X", "project_ids": [PROJ_A]}
    assert alice.post("/events", json=body).status_code == 200
    assert bob.post("/events", json=body).status_code == 404           # not a member of 500
    assert alice.post("/events", json={"title": "Y", "project_ids": [PROJ_B]}).status_code == 404


def test_event_attach_invisible_contact_denied(alice, contacts):
    """Alice can't attach a Bob-only contact she can't see to her event."""
    body = {"title": "Z", "project_ids": [PROJ_A], "contact_ids": [contacts["bob_keep"]]}
    assert alice.post("/events", json=body).status_code == 404


def test_event_set_primary_must_be_filed(alice, events):
    e = events["alice"]
    assert alice.patch(f"/events/{e}", json={"primary_project_id": PROJ_B}).status_code == 422


def test_event_mutate_delete_isolation(alice, bob, events):
    e = events["alice"]
    assert bob.patch(f"/events/{e}", json={"title": "hax"}).status_code == 404
    assert bob.delete(f"/events/{e}").status_code == 404
    assert alice.patch(f"/events/{e}", json={"title": "ok"}).status_code == 200
