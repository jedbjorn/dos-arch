#!/usr/bin/env python3
"""
Migration 007: shell groups — a lightweight permission boundary.

Adds three tables:
  - shell_groups        the group (slug, name, is_admin flag)
  - shell_group_members shell <-> group, flat membership
  - project_groups      project <-> group, many-to-many

A shell sees only the projects in the groups it belongs to. Membership is
shell-level (not user-level): one user may own several shells with different
group membership. An is_admin group's members bypass scoping.

Seeds the substrate's current partition:
  - group "admin" -> shells CC, Forge   -> is_admin=1, bypasses project scoping
  - group "rst"   -> shell Rester (rst) -> project rst-migration
  - group "core"  -> (no shells yet)    -> projects ami, dos_template

Idempotent: safe to run multiple times.

Usage:
    python3 shell_core/migrations/007_shell_groups.py <path-to-db>
"""
import sqlite3
import sys
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS shell_groups (
    group_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    slug        TEXT    NOT NULL UNIQUE,
    name        TEXT    NOT NULL,
    description TEXT,
    is_admin    INTEGER NOT NULL DEFAULT 0,
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS shell_group_members (
    membership_id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id      INTEGER NOT NULL REFERENCES shell_groups(group_id),
    shell_id      INTEGER NOT NULL REFERENCES shells(shell_id),
    added_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted    INTEGER NOT NULL DEFAULT 0,
    UNIQUE (group_id, shell_id)
);
CREATE TABLE IF NOT EXISTS project_groups (
    project_group_id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id   INTEGER NOT NULL REFERENCES shell_groups(group_id),
    project_id INTEGER NOT NULL REFERENCES projects(project_id),
    added_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    UNIQUE (group_id, project_id)
);
CREATE INDEX IF NOT EXISTS idx_shell_group_members_shell
    ON shell_group_members(shell_id);
CREATE INDEX IF NOT EXISTS idx_project_groups_group
    ON project_groups(group_id);
"""

# group slug -> (name, description, is_admin, [shell shortnames], [project shortnames])
SEED = {
    "admin": (
        "Admin",
        "Full-access shells — bypass project scoping; full (non-API-restricted) tooling.",
        1,
        ["cc", "forge"],
        [],
    ),
    "rst": (
        "RST Migration",
        "Rester's specialized C#/WPF Revit add-in migration.",
        0,
        ["rst"],
        ["rst-migration"],
    ),
    "core": (
        "Core",
        "General substrate and product work.",
        0,
        [],
        ["ami", "dos_template"],
    ),
}


def main(db_path):
    db = Path(db_path)
    if not db.exists():
        print(f"ERROR: db not found: {db}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(db)
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON")

    actions = []

    tables_existed = cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='shell_groups'"
    ).fetchone() is not None
    cur.executescript(SCHEMA)
    if not tables_existed:
        actions.append("created shell_groups, shell_group_members, project_groups")

    # Resolve shortname -> id maps once.
    shell_id = {r[0]: r[1] for r in cur.execute("SELECT shortname, shell_id FROM shells")}
    project_id = {r[0]: r[1] for r in cur.execute("SELECT shortname, project_id FROM projects")}

    for slug, (name, desc, is_admin, shells, projects) in SEED.items():
        row = cur.execute(
            "SELECT group_id FROM shell_groups WHERE slug=?", (slug,)
        ).fetchone()
        if row is None:
            cur.execute(
                "INSERT INTO shell_groups (slug, name, description, is_admin) "
                "VALUES (?,?,?,?)",
                (slug, name, desc, is_admin),
            )
            gid = cur.lastrowid
            actions.append(f"created group '{slug}'")
        else:
            gid = row[0]

        for sn in shells:
            sid = shell_id.get(sn)
            if sid is None:
                print(f"WARNING: shell '{sn}' not found, skipping", file=sys.stderr)
                continue
            if cur.execute(
                "SELECT 1 FROM shell_group_members WHERE group_id=? AND shell_id=?",
                (gid, sid),
            ).fetchone() is None:
                cur.execute(
                    "INSERT INTO shell_group_members (group_id, shell_id) VALUES (?,?)",
                    (gid, sid),
                )
                actions.append(f"added shell '{sn}' to '{slug}'")

        for pn in projects:
            pid = project_id.get(pn)
            if pid is None:
                print(f"WARNING: project '{pn}' not found, skipping", file=sys.stderr)
                continue
            if cur.execute(
                "SELECT 1 FROM project_groups WHERE group_id=? AND project_id=?",
                (gid, pid),
            ).fetchone() is None:
                cur.execute(
                    "INSERT INTO project_groups (group_id, project_id) VALUES (?,?)",
                    (gid, pid),
                )
                actions.append(f"linked project '{pn}' to '{slug}'")

    conn.commit()
    conn.close()

    if actions:
        print(f"[007_shell_groups] {db}: {'; '.join(actions)}")
    else:
        print(f"[007_shell_groups] {db}: already migrated, no-op")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    main(sys.argv[1])
