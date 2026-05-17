---
name: surface_catalogue
description: Surface the substrate catalogue (dr_*) on demand. Run before grepping the codebase to find what exists.
category: workflow
common: 1
---
# surface_catalogue

Surface the dr_* catalogue on demand — print every catalogued component
(routes, routers, deps, libs, services, repos, files, automations, env)
grouped by ref_table, with optional filtering. Runs before you grep the
codebase to find something.

## Quick reference

```bash
# Full listing (~111 rows today)
make catalogue

# Substring filter on name + ref_table (e.g. find anything related to flags)
make catalogue ARGS="flag"

# One ref_table only
make catalogue ARGS="--table dr_api"

# Per-shell view (uses v_shell_catalogue, includes role)
make catalogue ARGS="--shell 1"

# Combined
make catalogue ARGS="--shell 1 --table dr_api flag"
```

Or call the script directly (no `ARGS=` wrapper):

```bash
python3 shell_core/scripts/catalogue.py flag
python3 shell_core/scripts/catalogue.py --table dr_services
python3 shell_core/scripts/catalogue.py --shell 1 --table dr_api
```

## When to use

- Cold start — orienting in an unfamiliar substrate. One query beats many `find`/`grep`/`Read` calls.
- "Where does X live?" — `make catalogue ARGS="<X>"` searches names + ref_tables.
- "Is there an API for Y?" — beats reading all five router files.
- "What auto-runs in this substrate?" — `make catalogue ARGS="--table dr_automations"`.
- "What env vars matter?" — `make catalogue ARGS="--table dr_env"`.

The catalogue auto-syncs on API startup. If something looks stale, run
`make db-sync` first.

See `catalogue_sync` skill for the full sync pipeline and `db_map` for
direct SQL queries against `v_dr_catalogue` / `v_shell_catalogue`.

## Output shape

Grouped by ref_table, name in left column (truncated at 36 chars),
description_short in right column. Per-shell mode adds a `[role: X]` tail
when the link has a role annotation.
