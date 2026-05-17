---
name: db_patch
description: Patch SQL queries and Pydantic models in main.py. Includes targeted context load, sibling pattern scan, fix, restart/smoke-test, and post-patch messaging.
category: workflow
common: 0
---
# db_patch

- **skill_id:** 33
- **category:** workflow
- **common:** 0
- **description:** Patch SQL queries and Pydantic models in main.py. Includes targeted context load, sibling pattern scan, fix, restart/smoke-test, and post-patch messaging.

---

# db_patch — Workflow Skill

**Dev_Ref discipline:** Pre-change check `dr_*` (shell_db.db) for current state. Post-change write `dr_log` row (≤50 char summary, session_id).

**Trigger:** Any patch to SQL queries or Pydantic models in `main.py`. Use when fixing endpoint behavior, not schema changes (use database-migrations for schema).

---

## Step 1 — Context load

Grep for the affected endpoint(s) by route to get line numbers, then read ±50 lines:
```bash
grep -n "@app.patch\|@app.post\|@app.delete\|@app.get" shell_core/api/main.py | grep "<route-keyword>"
```

Read:
- The endpoint function
- The Pydantic model(s) it uses
- Any SQL helper constants it references (e.g. FLAG_DETAIL_SQL)
- Live table schema for any table the SQL touches:
```python
import sqlite3
db = sqlite3.connect('shell_core/shell_db.db')
print(db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='<table>'").fetchone()[0])
```

---

## Step 2 — Reproduce

Before writing any code, confirm the bug is real with a live API call against a real row.

```bash
UKEY=$(python3 -c "import sqlite3; db=sqlite3.connect('shell_core/shell_db.db'); db.row_factory=sqlite3.Row; print(db.execute('SELECT api_key FROM users WHERE user_id=1').fetchone()[0])")
curl -sk -X PATCH "https://localhost:8000/<endpoint>" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $UKEY" \
  -d '{"<one-field>": "<value>"}' | python3 -m json.tool
```

Confirm the broken behavior in the response. Record what field(s) are wrong and what they should be.
If the bug cannot be reproduced, stop and flag to FnB before patching.

---

## Step 3 — Pattern scan

Grep for the same bug pattern across sibling endpoints before writing any code.

Examples:
- NULLIF without COALESCE: `grep -n "NULLIF" shell_core/api/main.py`
- Full-replacement UPDATE: look for UPDATE blocks missing COALESCE on all fields
- Missing field in model: grep for similar models in the same endpoint family

Fix all instances found in one pass. Do not patch one endpoint and leave siblings broken.

---

## Step 4 — Patch

Make the fix. Keep it minimal — only change what the bug requires.

---

## Step 5 — Verify

```bash
pm2 restart api && sleep 2 && pm2 logs api --lines 10 --nostream
```

Confirm clean startup (no import errors, `Application startup complete`).

**Fix test:** repeat the reproduce call from Step 2. Confirm the broken field(s) are now correct.

**Regression test:** for each sibling endpoint touched in Step 3, send a partial PATCH and verify unset fields are preserved. Use real rows from the DB — pick rows that have non-null values for the fields being tested.

```bash
# Check DB state before and after each call
python3 -c "import sqlite3; db=sqlite3.connect('shell_core/shell_db.db'); db.row_factory=sqlite3.Row; print(dict(db.execute('SELECT * FROM <table> WHERE <id>=<val>').fetchone()))"
```

If any regression test fails: revert the patch, re-diagnose, do not ship.

---

## Step 6 — Post-patch

1. Append to the active session narrative (what was broken, what was fixed, siblings checked):
   ```python
   import sqlite3
   con = sqlite3.connect('/path/to/dos-arch/shell_core/shell_db.db')
   aid = con.execute("SELECT active_archive_id FROM shells WHERE shell_id=1").fetchone()[0]
   line = "[HH:MM] db_patch — <what broke, what fixed, siblings checked>"
   con.execute("UPDATE shell_memory_archives SET full_narrative = COALESCE(full_narrative,'') || char(10) || ? WHERE archive_id=?", (line, aid))
   con.commit()
   ```
2. If the fix came from another shell's bug report (peer ecosystem only): send a `shell_messages` row summarising what was fixed and whether related issues were found clean.
3. If the API contract changed (new fields, renamed params, new endpoints): run `api_sync` skill.

---

## Step 7 — Report to partner

Summarise the patch to Jed in plain language:

- **What was broken** — one sentence describing the bug and its impact
- **What was fixed** — what changed in the code
- **Siblings** — any other endpoints found with the same pattern (fixed or confirmed clean)
- **Tests** — repro confirmed, fix confirmed, regressions clean (or any caveats)
- **Follow-up** — any related issues deferred or flagged for future work

