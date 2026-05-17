#!/usr/bin/env python3
"""
Migration 006: lift IDENTITY out of system_prompt into shell columns.

Adds `owner` and `role` columns to `shells`. Parses each shell's existing
system_prompt for its `## IDENTITY` block, extracts Owner/Role into the new
columns, and strips the block (heading + table + trailing horizontal rule)
from system_prompt.

Mandate, Name, Shortname rows are dropped silently — those duplicate the
existing `mandate`, `display_name`, `shortname` columns.

Forge-style shells (system_prompt without an `## IDENTITY` heading) are
untouched.

Idempotent: skips ALTER if columns already present; skips strip if block
already absent. Aborts with a clear error if a shell has an IDENTITY block
the parser can't decode — surface and fix manually rather than silently
mangling identity data.

Usage:
    python3 shell_core/migrations/006_shell_identity_columns.py <path-to-db>
"""
import re
import sqlite3
import sys
from pathlib import Path


IDENTITY_RE = re.compile(
    r"\n##\s+IDENTITY\s*\n"          # heading
    r"(?:.*?\n)*?"                    # table rows (lazy)
    r"\|\s*\*\*Mandate\*\*\s*\|.*?\n" # last row anchor
    r"\s*\n"                          # blank line
    r"---\s*\n",                      # trailing rule
    re.MULTILINE,
)

ROW_RE = re.compile(r"^\|\s*\*\*(Owner|Role)\*\*\s*\|\s*(.+?)\s*\|\s*$", re.MULTILINE)


def _columns_exist(con: sqlite3.Connection) -> bool:
    cols = {r[1] for r in con.execute("PRAGMA table_info(shells)").fetchall()}
    return "owner" in cols and "role" in cols


def _add_columns(con: sqlite3.Connection) -> None:
    cols = {r[1] for r in con.execute("PRAGMA table_info(shells)").fetchall()}
    if "owner" not in cols:
        con.execute("ALTER TABLE shells ADD COLUMN owner TEXT")
    if "role" not in cols:
        con.execute("ALTER TABLE shells ADD COLUMN role TEXT")


def _process_shell(shell_id: int, display_name: str, system_prompt: str):
    """Returns (new_system_prompt, owner, role) or None if no IDENTITY block."""
    if "## IDENTITY" not in system_prompt:
        return None

    m = IDENTITY_RE.search("\n" + system_prompt)
    if not m:
        raise RuntimeError(
            f"shell_id={shell_id} ({display_name}): IDENTITY heading present "
            f"but block does not match expected shape (heading → table ending "
            f"with **Mandate** row → blank line → ---). Inspect manually."
        )

    block = m.group(0)
    fields = dict(ROW_RE.findall(block))
    owner = (fields.get("Owner") or "").strip() or None
    role = (fields.get("Role") or "").strip() or None

    # Strip the block (we matched against "\n" + system_prompt, so adjust)
    stripped = ("\n" + system_prompt).replace(block, "\n", 1).lstrip("\n")

    # Fix stale "IDENTITY below" prose — the IDENTITY block is no longer in
    # system_prompt; it's rendered above by run.py from columns.
    stripped = stripped.replace(
        "treat IDENTITY below as placeholder",
        "treat the IDENTITY block as placeholder",
    )

    return stripped, owner, role


BOOTSTRAP_OLD_SECTION_2 = """## 2. Mandate

Ask the FnB:
- What is this shell's actual role? (full-stack / backend / frontend /
  reviewer / data / ops / etc.)
- One sentence on the shell's mandate — what it is responsible for, what
  success looks like.

UPDATE `shells.mandate` accordingly."""

BOOTSTRAP_NEW_SECTION_2 = """## 2. Role & Mandate

Ask the FnB:
- What is this shell's role? (full-stack / backend / frontend / reviewer /
  data / ops / etc.) One short phrase.
- One sentence on the shell's mandate — what it is responsible for, what
  success looks like.

UPDATE `shells.role` and `shells.mandate` accordingly."""

BOOTSTRAP_OLD_OWNER_BLOCK = """Update the user row if the operator wants the placeholder personalized:
```python
import sqlite3
con = sqlite3.connect("shell_core/shell_db.db")
con.execute(
    "UPDATE users SET display_name=?, email=?, initials=? WHERE user_id=1",
    (display_name, email, initials),
)
con.commit()
```"""

BOOTSTRAP_NEW_OWNER_BLOCK = """Update both the substrate user row (substrate-level identity) and this
shell's `owner` column (shell-facing label, what the shell sees as "owner"):

```python
import sqlite3
con = sqlite3.connect("shell_core/shell_db.db")
con.execute(
    "UPDATE users SET display_name=?, email=?, initials=? WHERE user_id=1",
    (display_name, email, initials),
)
con.execute(
    "UPDATE shells SET owner=? WHERE shell_id=<self>",
    (display_name,),
)
con.commit()
```"""


def _update_bootstrap_skill(con: sqlite3.Connection) -> None:
    row = con.execute(
        "SELECT skill_id, content FROM skills WHERE name='bootstrap_interview'"
    ).fetchone()
    if row is None:
        print("  bootstrap_interview skill not found — skipping skill content update")
        return
    skill_id, content = row["skill_id"], row["content"] or ""
    if "## 2. Role & Mandate" in content:
        print("  bootstrap_interview: already updated, skipping")
        return

    new_content = content
    owner_hit = BOOTSTRAP_OLD_OWNER_BLOCK in new_content
    section_hit = BOOTSTRAP_OLD_SECTION_2 in new_content
    if not (owner_hit and section_hit):
        # Skill content has diverged from the substrate template — could be a
        # local rewrite or an older schema-era variant. Don't fail the whole
        # migration; surface a warning so the shell row updates still land.
        print(
            f"  bootstrap_interview: anchors not found "
            f"(owner_block={owner_hit}, section_2={section_hit}); "
            f"skipping skill content update — fix manually if needed",
            file=sys.stderr,
        )
        return

    new_content = new_content.replace(BOOTSTRAP_OLD_OWNER_BLOCK, BOOTSTRAP_NEW_OWNER_BLOCK, 1)
    new_content = new_content.replace(BOOTSTRAP_OLD_SECTION_2, BOOTSTRAP_NEW_SECTION_2, 1)
    con.execute("UPDATE skills SET content=? WHERE skill_id=?", (new_content, skill_id))
    print(
        f"  bootstrap_interview: rewrote owner block + section 2 "
        f"({len(content)} → {len(new_content)} chars)"
    )


def main(db_path: str) -> None:
    db = Path(db_path)
    if not db.exists():
        print(f"ERROR: db not found: {db}", file=sys.stderr)
        sys.exit(1)

    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row

    already = _columns_exist(con)
    _add_columns(con)
    if already:
        print(f"[006_shell_identity_columns] {db}: owner/role columns already present")
    else:
        print(f"[006_shell_identity_columns] {db}: added owner, role columns")

    rows = con.execute(
        "SELECT shell_id, display_name, system_prompt, owner, role FROM shells ORDER BY shell_id"
    ).fetchall()

    touched = 0
    for r in rows:
        result = _process_shell(r["shell_id"], r["display_name"], r["system_prompt"] or "")
        if result is None:
            print(f"  shell_id={r['shell_id']} ({r['display_name']}): no IDENTITY block, skipped")
            continue
        new_prompt, owner, role = result
        # Preserve any owner/role already set; only fill if currently NULL
        new_owner = r["owner"] if r["owner"] else owner
        new_role = r["role"] if r["role"] else role
        con.execute(
            "UPDATE shells SET system_prompt=?, owner=?, role=? WHERE shell_id=?",
            (new_prompt, new_owner, new_role, r["shell_id"]),
        )
        touched += 1
        print(
            f"  shell_id={r['shell_id']} ({r['display_name']}): "
            f"owner={new_owner!r}, role={new_role!r}, system_prompt stripped "
            f"({len(r['system_prompt'])} → {len(new_prompt)} chars)"
        )

    _update_bootstrap_skill(con)

    con.commit()
    con.close()
    print(f"[006_shell_identity_columns] {db}: {touched} shell(s) updated")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    main(sys.argv[1])
