---
name: db_map
description: Schema map + reusable SQL patterns for shell_db.db. Check before composing any DB query.
category: workflow
common: 1
---
# db_map

- **category:** workflow
- **common:** 0 (local — uses sqlite3)
- **description:** Schema map + reusable SQL patterns for shell_db.db. Check before composing any DB query.

---

## TRIGGER

About to query `/path/to/dos-arch/shell_core/shell_db.db` (read or write). Read this skill **first** before composing the query.

If a matching pattern exists below → use it.
If not → discover with `PRAGMA table_info(<t>)`, run the query, then surface to FnB: *"new pattern — add to db_map?"*

---

## DB PATH

`/path/to/dos-arch/shell_core/shell_db.db`

---

## HOW TO RUN QUERIES

`sqlite3` CLI is **NOT installed** on this host. Use `python3` + the stdlib `sqlite3` module for every query in this skill (and any skill that delegates to it).

```python
import sqlite3
con = sqlite3.connect('/path/to/dos-arch/shell_core/shell_db.db')
cur = con.cursor()
cur.execute("...")           # any of the patterns below
print(cur.fetchall())        # for reads
con.commit()                 # for writes
```

One-liner form for ad-hoc:
```bash
python3 -c "import sqlite3; c=sqlite3.connect('/path/to/dos-arch/shell_core/shell_db.db'); print(c.execute('SELECT ...').fetchall())"
```

The SQL bodies in the sections below are correct as written — only the wrapper changes.

---

## SCHEMA MAP

| Table | Columns |
|---|---|
| `shells` | shell_id, display_name, shortname, mandate, system_prompt, current_state, connections, api_endpoints, lineage_seed, browser_chat, ignore_messages, ignore_messages_since, has_identity, active_archive_id, user_id, session_payload |
| `projects` | project_id, shortname, **title** (not display_name), purpose, standing, status, is_deleted, created_at |
| `project_shells` | project_shell_id, project_id, shell_id, role, added_date, is_deleted |
| `skills` | skill_id, **name** (not skill_name), description, file_path, category, content, command, common, is_deleted |
| `shell_skills` | shell_skill_id, shell_id, skill_id  *(table name: `shell_skills`, NOT `skill_shells`)* |
| `shell_identity_entries` | entry_id, shell_id, **kind** ('seed' or 'lns'), entry_date, source_tag, body, created_at, retired_at, is_deleted |
| `shell_memory_archives` | archive_id, shell_id, session_id, date, full_narrative |
| `shell_decisions` | decision_id, shell_id, decision_date, priority, decision, rationale, parent_decision_id, is_deleted, created_at |
| `flags` | flag_id, display_name, priority, description, created_date, resolved_date, resolved, shell_id, start_date, resolution_notes, is_deleted, parent_flag_id, estimated_days |
| `dr_log` | log_id, ref_table, ref_id, change_type, change_summary, session_id, archive_ref, changed_at |

**Naming gotchas (real misses):**
- `projects.title` — not `display_name`
- `skills.name` — not `skill_name`
- Table `shell_skills` — not `skill_shells`

---

## CATALOGUE (live state index)

The dr_* family + `shell_dr_link` + two views form a navigable index of
what exists in the substrate. Source-of-truth is the underlying code/config;
catalogue rows are populated by `shell_core/scripts/dr_sync.py` (auto-fires
on FastAPI startup, or on demand via `make db-sync`). See `catalogue_sync`
skill for the full pipeline.

| Table / view | Holds |
|---|---|
| `v_dr_catalogue` | Substrate-wide projection: `(ref_table, ref_id, name, description_short)` across all 9 typed tables |
| `v_shell_catalogue` | Per-shell binding view: `(shell_id, ref_table, ref_id, name, description_short, role)` |
| `shell_dr_link` | Per-shell link: `link_id, shell_id, ref_table, ref_id, role` |
| `dr_router` | Router files: `name, description_short, file_path, prefix` |
| `dr_api` | Routes: `router_id (FK), name, description_short, path, method, purpose` |
| `dr_dependencies` | npm + pip deps: `project, name, description_short, version, kind` |
| `dr_lib` | Backend (api/common/*) + frontend (ui/src/lib/*): `kind, name, description_short, location` |
| `dr_services` | pm2 apps: `name, description_short, kind, location` |
| `dr_repo` | Tracked git repos: `name, description_short, path, remote` |
| `dr_filepath` | Notable paths (curated): `name, description_short, path, kind` |
| `dr_automations` | Scheduled/triggered jobs (curated): `name, description_short, trigger_kind, schedule` |
| `dr_env` | Env vars (curated, no values stored): `name, description_short, scope, location, is_secret` |

## COMMON QUERIES (catalogue)

```sql
-- Index card for everything in the substrate
SELECT ref_table, name, description_short FROM v_dr_catalogue ORDER BY ref_table, name;

-- "What APIs exist for editing flags?"
SELECT name, description_short FROM v_dr_catalogue
WHERE ref_table = 'dr_api' AND name LIKE '%flag%';

-- "What's bound to this shell?"
SELECT ref_table, name, description_short, role FROM v_shell_catalogue WHERE shell_id = 1;

-- "Where does X live?"  (filepath lookup without grep)
SELECT path, kind, description_short FROM dr_filepath WHERE name LIKE '%db%';

-- "What env vars does this substrate care about?"
SELECT name, scope, is_secret, description_short FROM dr_env;
```

---

## COMMON QUERIES (read)

```sql
-- identity bundle
SELECT shell_id, display_name, mandate, current_state, active_archive_id FROM shells WHERE shell_id=1;

-- active seed entries for CC
SELECT entry_id, entry_date, body FROM shell_identity_entries
WHERE shell_id=1 AND kind='seed' AND is_deleted=0 AND retired_at IS NULL
ORDER BY entry_date, entry_id;

-- active L&S count
SELECT COUNT(*) FROM shell_identity_entries
WHERE shell_id=1 AND kind='lns' AND is_deleted=0 AND retired_at IS NULL;

-- active projects for a shell
SELECT p.shortname, p.title, p.purpose, ps.role
FROM projects p JOIN project_shells ps ON ps.project_id=p.project_id
WHERE ps.shell_id=1 AND p.is_deleted=0 AND ps.is_deleted=0;

-- skills assigned to a shell
SELECT s.name, s.description FROM skills s
JOIN shell_skills ss ON ss.skill_id=s.skill_id
WHERE ss.shell_id=1 AND s.is_deleted=0 ORDER BY s.name;

-- open flags
SELECT flag_id, display_name, priority, description FROM flags
WHERE shell_id=1 AND resolved=0 AND is_deleted=0 ORDER BY created_date;

-- session_payload (assembled identity)
SELECT session_payload FROM shells WHERE shell_id=1;

-- skill content lookup
SELECT content FROM skills WHERE name=? AND is_deleted=0;
```

## COMMON QUERIES (write)

```sql
-- update current_state (≤280 chars, trigger-enforced)
UPDATE shells SET current_state=? WHERE shell_id=1;

-- append to session narrative
UPDATE shell_memory_archives
SET full_narrative = full_narrative || char(10) || ?
WHERE archive_id=?;

-- add seed (cap 10, trigger-enforced)
INSERT INTO shell_identity_entries (shell_id, kind, entry_date, source_tag, body)
VALUES (1, 'seed', date('now'), NULL, ?);

-- retire L&S (frees a slot)
UPDATE shell_identity_entries SET retired_at=datetime('now')
WHERE entry_id=? AND shell_id=1 AND kind='lns';

-- log a decision (M only)
INSERT INTO shell_decisions (shell_id, decision_date, priority, decision, rationale)
VALUES (1, date('now'), 'M', ?, ?);

-- open flag
INSERT INTO flags (display_name, priority, description, created_date, shell_id)
VALUES (?, ?, ?, date('now'), 1);

-- close flag
UPDATE flags SET resolved=1, resolved_date=date('now'), resolution_notes=?
WHERE shell_id=1 AND display_name=?;
```

---

## DISCOVERY FALLBACK

When the schema doesn't match — find tables and columns:

```sql
-- Find a table by partial name
SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%kw%';

-- Get columns for any table
PRAGMA table_info(<table>);
```

(Wrap with the python3 connector from the HOW TO RUN QUERIES section above.)

---

## GROWTH PROTOCOL

Every time a new query pattern lands (read or write), surface to FnB:
> "new pattern — add to db_map?"

If yes → UPDATE skills.content via `skill_management` UPDATE flow.
