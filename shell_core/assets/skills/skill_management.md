---
name: skill_management
description: Skill lifecycle for the substrate — create, update, delete, assign. Interview-driven.
category: workflow
common: 1
---
# skill_management

- **category:** workflow
- **common:** 0
- **description:** Skill lifecycle for the substrate — create, update, delete, assign. Interview-driven.

---

# skill_management

**Dev_Ref discipline:** Pre-change check `dr_*` (shell_db.db) for current state. Post-change write `dr_log` row (≤50 char summary, session_id).

**Trigger:** FnB says any of:
- Create: "create a skill", "new skill", "we need a skill", "add a skill"
- Update: "update skill X", "edit skill X", "rewrite skill X"
- Delete: "retire skill X", "delete skill X", "hard delete skill X"
- Assign: "assign skill X to {shell}", "unassign skill X from {shell}"

All DB ops via the python3 `sqlite3` stdlib module against `/path/to/dos-arch/shell_core/shell_db.db` — see `db_map`.

---

## SCOPE

While the substrate runs a single shell, every assignment lands on that shell. The `common` flag is preserved for forward-compat (when peer shells join, `common=1` will mark API-only skills safe for non-host shells), but every skill authored today defaults to `common=0`.

When peers / GUI consumers exist, the additional discipline (live-shell guards, API-only prelude, fork mode) is documented in the v0.1 history of this skill — re-add when needed, not before.

---

## MODE DETECTION

| Phrase                         | Mode      |
|--------------------------------|-----------|
| create / new / we need / add   | CREATE    |
| update / edit / rewrite        | UPDATE    |
| retire / delete / hard delete  | DELETE    |
| assign / unassign              | ASSIGNMENT|

If ambiguous, ask FnB which mode.

---

## CREATE — Interview

Ask one at a time. Wait for each answer.

**Q1 — What it does.** One-line description (goes in `skills.description`), then 1–3 sentences on purpose (opens the content body).

**Q2 — Trigger phrases.** What FnB says to fire it.

**Q3 — Args.** Does it take arguments? If yes, list them (e.g. `[date]`, `[n days]`).
- `command` column: stored bare, no args (e.g. `-- audit memory`).
- `description` column: starts with example invocation (e.g. ``-- audit memory` — Audit what's loaded at session start.`).
- If args required: skill content must instruct CC to interview for missing args before any write — never guess.

**Q4 — Category.** workflow / platform / token. Default workflow.

**Q5 — State it writes.** Tables / files / endpoints it mutates. Used for schema contract check + post-action review.

**Q6 — Idempotent?** Can it fire twice without damage? Single-shot needs a guard — document it.

**Q7 — Conflict check** (auto, no FnB prompt):
```python
import sqlite3
con = sqlite3.connect('/path/to/dos-arch/shell_core/shell_db.db')
print(con.execute("SELECT skill_id, name, is_deleted FROM skills WHERE name=?", ['{name}']).fetchall())
```
- No hit → proceed.
- Hit, `is_deleted=0` → ask FnB: overwrite / rename new / abort?
- Hit, `is_deleted=1` → ask FnB: restore (UPDATE is_deleted=0 + content) or create fresh?

### Pre-INSERT guards

1. **Schema contract.** Any table names in Q5 must exist in the live DB. Any API endpoints must match `grep -E "^@(?:app|router)\." shell_core/api/main.py shell_core/api/routers/*.py`. Reject unknown references and ask FnB.
2. **Dev_Ref directive.** If the skill touches code / schema / services / libs / deps / automations (any item from Q5 that's not pure read or pure messaging), prepend this header to content:
   ```
   **Dev_Ref discipline:** Pre-change check `dr_*` (shell_db.db) for current state. Post-change write `dr_log` row (≤50 char summary, session_id).
   ```

### Execute

```python
import sqlite3
con = sqlite3.connect('/path/to/dos-arch/shell_core/shell_db.db')
cur = con.cursor()
cur.execute("INSERT INTO skills (name, description, category, content, common, is_deleted) VALUES (?, ?, ?, ?, 0, 0)",
            ["{name}", "{description}", "{category}", "{content}"])
skill_id = cur.lastrowid
cur.execute("INSERT INTO shell_skills (shell_id, skill_id) VALUES (1, ?)", [skill_id])
cur.execute("INSERT INTO dr_log (ref_table, ref_id, change_type, change_summary, session_id) VALUES ('skills', ?, 'create', ?, ?)",
            [skill_id, f"created skill {{name}}"[:50], "{session_id}"])
con.commit()
print(f"skill_id={skill_id}")
```

### Post-action

- If Q5 includes new tables or endpoints, run `api_sync` skill.
- If structural enough to warrant it, log a `shell_decisions` row via the `decision` skill.
- Report to FnB: `skill_id`, name, what it does, next-action if any.

---

## UPDATE

1. Resolve `skill_id`:
   ```python
   import sqlite3
   con = sqlite3.connect('/path/to/dos-arch/shell_core/shell_db.db')
   print(con.execute("SELECT skill_id, name, is_deleted FROM skills WHERE name=?", ['{name}']).fetchall())
   ```
   Multiple hits → ask which. Zero hits or all `is_deleted=1` → redirect to CREATE.

2. Apply Pre-INSERT guards from CREATE (schema contract, Dev_Ref header).

3. Write:
   ```python
   con.execute("UPDATE skills SET content=?, description=COALESCE(?, description) WHERE skill_id=?",
               ["{new_content}", "{new_description_or_None}", skill_id])
   con.execute("INSERT INTO dr_log (ref_table, ref_id, change_type, change_summary, session_id) VALUES ('skills', ?, 'update', ?, ?)",
               [skill_id, f"updated skill {{name}}"[:50], "{session_id}"])
   con.commit()
   ```

---

## DELETE

Two flavours. Default to **hard delete** while the substrate is single-shell — no historical consumers to preserve a reference for.

**Hard delete** (preferred):
1. Resolve skill_id.
2. Confirm with FnB.
3. Snapshot DB first if doing a multi-skill purge — `db_backup` skill.
4. Execute:
   ```python
   con.execute("INSERT INTO dr_log (ref_table, ref_id, change_type, change_summary, session_id) VALUES ('skills', ?, 'delete', ?, ?)",
               [skill_id, f"hard delete: {{name}}"[:50], "{session_id}"])
   con.execute("DELETE FROM shell_skills WHERE skill_id=?", [skill_id])
   con.execute("DELETE FROM skills WHERE skill_id=?", [skill_id])
   con.commit()
   ```

**Soft delete** (use when something downstream — docs, seed entry, decision log — references the skill by name and you want the row preserved as historical context):
```python
con.execute("UPDATE skills SET is_deleted=1 WHERE skill_id=?", [skill_id])
con.execute("INSERT INTO dr_log (ref_table, ref_id, change_type, change_summary, session_id) VALUES ('skills', ?, 'delete', ?, ?)",
            [skill_id, f"soft-retire: {{name}}"[:50], "{session_id}"])
con.commit()
```
`shell_skills` rows stay intact — the JOIN filter on `is_deleted=0` handles exclusion.

---

## ASSIGNMENT

**Assign:**
```python
con.execute("INSERT INTO shell_skills (shell_id, skill_id) VALUES (?, ?)", [shell_id, skill_id])
con.commit()
```
Catch IntegrityError on duplicate. Today shell_id=1 is the only valid target.

**Unassign:**
```python
con.execute("DELETE FROM shell_skills WHERE shell_id=? AND skill_id=?", [shell_id, skill_id])
con.commit()
```

Loads on next session start (the SKILLS block in `shells/cc/CLAUDE.md` re-renders from `shell_skills` ⋈ `skills`).

---

## PITFALLS

- **Default `common`.** Always set explicitly on INSERT — column default is unreliable across SQLite versions. Today: always `common=0`.
- **Hardcoded paths.** Use absolute path `/path/to/dos-arch/shell_core/shell_db.db` in skill content rather than relative — skills run from varied cwd.
- **Arg defaults.** Store the `command` field bare (no embedded `[arg]` placeholders); put the example-with-args in `description`. UI picker prefills `command`; embedded placeholders confuse users.
- **Deleted name reuse.** Hard-deleted name is freely reusable. Soft-deleted name reuse needs care — check `is_deleted=1` rows first and decide restore-vs-fresh.
- **No fork mode (yet).** When peer shells join, FORK becomes useful (one skill, two variants — one with bash/DB, one API-only). Re-add the mode then. Don't pre-build it.
