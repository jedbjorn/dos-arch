---
name: db_backup
description: Snapshot the live DB to /db_backups/<project>/ before any structural change.
category: workflow
common: 1
---
# db_backup

- **category:** workflow
- **common:** 0
- **description:** Snapshot the live DB to ~/db_backups/<project>/ before any structural change. Atomic single-row edits don't need it — rollback covers them.

---

# DB Backup — Skill

**When to back up:**
- Schema change (CREATE / ALTER / DROP table or column)
- Bulk edit (multiple skills, multiple shells, multi-step rewrites)
- Laws section edit on any system_prompt
- Destructive query (DELETE without WHERE, mass UPDATE, TRUNCATE)
- Anything you couldn't undo with a single transaction rollback

Atomic single-row edits inside `BEGIN`/`COMMIT` don't need a backup — the rollback path covers them.

---

## Where backups live

Substrate convention: `~/db_backups/<PROJECT_NAME>/` on the host, where
`<PROJECT_NAME>` is the project directory name. The substrate ships with
`dos_shell_infra` baked in (`~/db_backups/dos_shell_infra/`) — when you fork
this substrate into a project clone, update the Makefile `BACKUP_DIR` and the
path below to your project's own dir so instances stay separate.

| Active instance     | Backup dir                                |
|---------------------|-------------------------------------------|
| dos_shell_infra     | ~/db_backups/dos_shell_infra/             |
| dos_template        | ~/db_backups/dos_template/                |
| <your project>      | ~/db_backups/<your project>/              |

---

## Backup

The fastest path is `make db-backup` from the project root — it timestamps and
writes to the configured `BACKUP_DIR`.

For an ad-hoc backup with a label:

```bash
PROJECT_NAME="dos_shell_infra"           # update for your fork
LABEL=<short_snake_case>                 # e.g. pre_skills_import, pre_laws_edit
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DEST="${HOME}/db_backups/${PROJECT_NAME}/shell_db.bak.${TIMESTAMP}_${LABEL}.db"
mkdir -p "$(dirname "${DEST}")"
cp shell_core/shell_db.db "${DEST}"
python3 -c "import sqlite3; print(sqlite3.connect('${DEST}').execute('PRAGMA integrity_check').fetchone()[0])"   # must print 'ok'
ls -la "${DEST}"
```

---

## Restore (if a change went wrong)

```bash
# Stop any DB writers first — make down  (or kill the API process):
make down
cp "${DEST}" shell_core/shell_db.db
python3 -c "import sqlite3; print(sqlite3.connect('shell_core/shell_db.db').execute('PRAGMA integrity_check').fetchone()[0])"
make up
```

---

## Cleanup

Backups accumulate. Periodic manual prune (no automation). Minimum keepers:
- The most recent backup per project
- Any tied to a major schema change (look in `dr_log` for context)
- One per month for older history if disk allows
