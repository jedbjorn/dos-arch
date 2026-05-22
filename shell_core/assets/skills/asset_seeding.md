---
name: asset_seeding
description: How DB seed data is organised — the assets/<domain>/ + _seed.toml convention, the generic seed_from_assets() seeder, and how to add a new seeded domain. Substrate-maintenance, admin shell.
category: workflow
common: 0
---
# asset_seeding

Seed data — the rows a fresh substrate DB needs to be usable — lives as
tracked text under `shell_core/assets/`, not as a prepacked binary DB.
Text assets diff, review, and merge; a binary `.db` does none of those.
The DB is rebuilt from `schema.sql` + these assets by `make bootstrap`.

One **domain** = one directory = one table. The seeder reads the
directory, the directory's manifest names the table, and the schema
defines the columns. All three must line up — and the seeder *enforces*
that they do.

## Layout

```
shell_core/assets/<domain>/
  _seed.toml      the contract — what table, how to map
  <name>.md       one file = one row (frontmatter + body)
  <name>.md
```

Skills and tools seed this way (`assets/skills/`, `assets/tools/`).

## The `_seed.toml` contract

```toml
table       = "skills"     # target table
match       = "name"       # column used for INSERT-missing-only dedup
body        = "content"    # column the file body is written to
body_format = "json"       # optional: 'text' (default) or 'json'
[const]                    # optional: columns set the same on every row
some_col    = "value"
```

- `body_format = "json"` makes the seeder run `json.loads` on the body —
  a malformed payload fails at `make bootstrap`, not at runtime.
- `[const]` is for columns genuinely constant across the whole domain.
  Columns that *vary per row* belong in each file's frontmatter, not
  here. Columns you name nowhere fall through to the schema default.

## The asset file

```
---
name: example
description: one-line summary
category: workflow
---
<body — markdown for prose domains, JSON for a JSON-spec domain>
```

Frontmatter is single-line `key: value` pairs; **each key is a column
name, 1:1**. The body (everything after the closing `---`) is written to
the `body` column verbatim.

## The seeder

`seed_from_assets(con, domain)` in `shell_core/scripts/db_init.py` is the
engine. Per domain it:

1. reads `_seed.toml`;
2. introspects the live schema (`PRAGMA table_info`) for the table's
   columns and their types — **the schema is the type authority**;
3. validates every key — manifest, `[const]`, and every file's
   frontmatter — against those columns;
4. coerces each frontmatter string to its column's type;
5. INSERTs rows missing by the `match` column.

It is **INSERT-missing-only** — it never UPDATEs. A local edit to a live
row survives a re-run; propagating a *change* to an existing row is a
migration's job, not the seeder's.

Anything that doesn't line up is a **hard error**, by file and key:

| Failure | Cause |
|---|---|
| table not in schema | `_seed.toml` `table` is wrong, or the migration didn't run |
| column not on table | a manifest or frontmatter key has no matching column |
| missing match key | a file's frontmatter omits the `match` column |
| body is not valid JSON | `body_format = "json"` and the body won't parse |

## Adding a new seeded domain

1. Add the table to `schema.sql` **and** a numbered migration in
   `shell_core/migrations/` (schema.sql is the fresh-install shape;
   migrations carry existing installs forward — keep both).
2. `mkdir shell_core/assets/<domain>/` and write its `_seed.toml`.
3. Drop one `*.md` per row.
4. Wire it into `bootstrap.py` — call `seed_from_assets(con, "<domain>")`
   (or a thin named wrapper, as `seed_skills` / `seed_tools` are).
5. Run the seeder against a throwaway DB built from `schema.sql` and
   confirm the row count before committing.

## Documented exceptions

Not everything fits the convention — two domains stay off it on purpose:

- **shells** — `ensure_forge` / `seed_sys_admin` stay bespoke. They need
  boot-time values an asset file can't carry: the first user's `user_id`,
  a template render, skill attachment. `assets/shells/*.md` exists, but
  bespoke functions consume it.
- **models** — a small, stable set; kept as the inline `_MODELS` literal
  in `db_init.py`. If it grows or starts to churn, move it onto the
  convention — `assets/models/` + `_seed.toml`, no new seeder code.

A post-seed step the generic seeder can't express — a template render, a
boot-time id, skill attachment — stays as explicit code in the domain's
wrapper; see `ensure_forge`. A domain may also carry extra manifest tables
its wrapper reads: `assets/tools/_seed.toml` has a `[skill_map]` the generic
seeder ignores and `seed_tools` consumes to scope each tool to its skill.
