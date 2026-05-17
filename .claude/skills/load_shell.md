---
name: load_shell
description: Pick a shell from this project's shell_db and load its identity (system_prompt, seed, the_laws, lessons_and_stances) into the current conversation. Re-run after /clear to restore identity.
---

# load_shell

Loads a shell's identity into the current conversation context. Conversation-only —
nothing on disk changes. Re-run after `/clear` to restore identity.

## What this skill does

1. Reads `shell_core/shell_db.db` and lists shells: `shell_id`, `shortname`, `mandate`.
2. Asks the human which shell to load (by shortname or shell_id) — unless arg passed.
3. Reads that shell's full identity columns and loads them into the conversation.
4. Confirms in chat: "I am `<display_name>`, `<shortname>`. Mandate: `<mandate>`."

## How to run

### Step 1 — list shells

```bash
sqlite3 -header -column shell_core/shell_db.db \
  "SELECT shell_id, shortname, mandate FROM shells ORDER BY shell_id"
```

If the host has no `sqlite3` CLI:

```bash
python3 -c "
import sqlite3
con = sqlite3.connect('shell_core/shell_db.db')
con.row_factory = sqlite3.Row
for r in con.execute('SELECT shell_id, shortname, mandate FROM shells ORDER BY shell_id'):
    print(f'{r[\"shell_id\"]:>3}  {r[\"shortname\"]:<12}  {r[\"mandate\"] or \"\"}')"
```

If the table is empty: tell the human "No shells defined yet — seed shells via the API or directly in `shell_db.db`." and stop.

### Step 2 — pick a shell

If the human passed a shortname or id as an arg, use it. Otherwise ask:
"Which shell to load? (shortname or shell_id)"

### Step 3 — load identity

```bash
python3 -c "
import sqlite3, json
con = sqlite3.connect('shell_core/shell_db.db')
con.row_factory = sqlite3.Row
# accept shortname OR shell_id
key = '<picked>'
row = con.execute(
    'SELECT * FROM shells WHERE shortname=? OR shell_id=?',
    (key, key if key.isdigit() else -1)
).fetchone()
print(json.dumps(dict(row), indent=2))"
```

Read the row. Adopt the identity by treating these columns as authoritative for
the rest of this conversation:

- `display_name`, `shortname`, `mandate` — who you are.
- `system_prompt` — your operating instructions.
- `the_laws` — non-negotiable rules.
- `seed` — identity-forming moments. Curated by the shell. Cap 10. Exempt from compression.
- `lessons_and_stances` — operating principles. Cap 20.
- `current_state`, `connections`, `api_endpoints` — context.
- `shell_decisions` table (rows where `shell_id = <yours>`) — running decision log.

### Step 4 — confirm

Output one line:
> "I am `<display_name>` (`<shortname>`). Mandate: `<mandate>`. Loaded from
> `shell_core/shell_db.db`. Run `/clear`-then-`load_shell` to re-load."

## Notes

- This skill writes nothing to disk.
- Shell identity lives in the DB, not on the filesystem. Edits to who-you-are go
  through the FastAPI `PATCH /shells/<id>` route (when the API is up) or direct
  SQL on `shell_db.db` (when it isn't).
- `/clear` wipes conversation context. Re-run this skill after `/clear` to
  restore identity. (No automatic re-load — keep memory architecture explicit.)
