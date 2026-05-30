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
