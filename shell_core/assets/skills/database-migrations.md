---
name: database-migrations
description: How to evolve the substrate's SQLite schema — author a migration file, keep schema.sql in sync, let it apply at recompose. Use when adding or altering a table, column, trigger, or running a data backfill.
category: workflow
common: 0
---
# database-migrations

How the substrate changes its own schema. A migration file is the **only**
way the live `shell_db.db` is altered — never hand-edit a running database.

---

## The pipeline

```
author    shell_core/migrations/NNN_name.sql   (+ matching schema.sql edit)
   │
operator  git pull                              (on the host)
   │
operator  ./install/api-up.sh   →   migrate.py applies pending migrations
   │                                (stop API → snapshot → apply → record → start)
live DB evolved
```

You **author** the migration — in your container, with the repo bind-mounted,
or hand it to the operator. The trusted recompose path **applies** it. No
shell runs `ALTER TABLE` against the live DB directly.

`shell_core/scripts/migrate.py` is the runner: it snapshots the DB, applies
each pending `migrations/*.sql` in numeric order in its own transaction,
records it in `schema_migrations`, and **halts on the first failure**. It
runs inside `install/api-up.sh` at every recompose, and on demand:

```bash
make migrate                 # apply pending migrations
make migrate ARGS=--status   # preview the pending set, apply nothing
```

---

## Authoring a migration

**1. Write `shell_core/migrations/NNN_name.sql`.**
- `NNN` — the next free zero-padded number. Files apply in filename order.
- Plain SQL — DDL, data, or both. **No `BEGIN`/`COMMIT`** in the file: the
  runner wraps each migration in one transaction.
- Forward-only. To undo a shipped migration, write a new one — never edit a
  migration that has already run anywhere.

**2. Update `shell_core/schema.sql` to match.** `schema.sql` is the canonical
fresh-install schema; `bootstrap.py` loads it and then stamps every
`migrations/*.sql` as already applied. So a migration's end state **must**
also be reflected in `schema.sql`, or fresh substrates and migrated ones
drift apart. Edit both in the same commit.

**3. Verify.** `make migrate ARGS=--status` should list it as pending. On a
non-production copy, `make migrate` applies it — confirm the schema is what
you intended before it ships.

---

## SQLite safety rules

- **Additive first.** `ADD COLUMN`, `CREATE TABLE`, `CREATE TRIGGER`,
  `CREATE INDEX` are clean. SQLite's `ALTER TABLE` is limited — to reshape a
  table (drop/retype a column on old SQLite, reorder, change constraints):
  create the new table, `INSERT INTO new SELECT … FROM old`, drop the old,
  rename — all within the one migration.
- **New columns: nullable or defaulted.** `ADD COLUMN … NOT NULL` with no
  default fails on a populated table. Add it nullable, backfill in the same
  migration.
- **DDL is transactional in SQLite** — a failed migration rolls back whole,
  and the runner snapshots to `~/db_backups/dos-arch/` first regardless.
- **Big backfills get their own migration.** Keep a substantial data
  transform separate from schema DDL — shorter transactions, smaller failure
  surface.
- **Renames: expand-contract.** Add the new column, backfill it, ship the
  code that uses it — then a *later* migration drops the old column. Never
  drop a column the running API still selects.

---

## Don't

- Don't hand-edit `shell_db.db` — every change is a migration file.
- Don't edit a migration that has already run — write a new one.
- Don't put transaction control inside a migration file — the runner owns it.
- Don't ship a migration without the matching `schema.sql` update.
