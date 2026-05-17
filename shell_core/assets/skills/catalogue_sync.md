---
name: catalogue_sync
description: How the dr_* catalogue stays in sync with substrate state — typed tables, populator targets, triggers, where to extend.
category: workflow
common: 0
---
# catalogue_sync

- **category:** workflow
- **description:** How the dr_* catalogue stays in sync with substrate state — typed tables, populator targets, triggers, where to extend.

The catalogue is a per-shell quick-reference index over the substrate's
real components (routes, services, deps, repos, libs, env vars, etc.).
Source of truth is always the underlying state (code/config); the catalogue
is a projection that auto-syncs via `shell_core/scripts/dr_sync.py`.

## Architecture

```
typed registries (one row per thing, all carry name + description_short)
  dr_repo, dr_filepath, dr_router, dr_api, dr_lib,
  dr_dependencies, dr_services, dr_automations, dr_env
        │
        │  FK by (ref_table, ref_id)
        ▼
shell_dr_link  (per-shell binding, optional `role` column)
        │
        ▼
v_dr_catalogue       — substrate-wide projection (name + description_short)
v_shell_catalogue    — per-shell, includes role annotation
```

Every typed row carries `name` + `description_short` (cap 100). That's the
"index card" projection. Type-specific fields stay on the typed rows for
deeper queries.

## Triggers

| Trigger | What runs |
|---|---|
| **API startup event** (every pm2/uvicorn restart) | `sync_all` — runs every wired sync target |
| **`make db-sync`** | Same — explicit on-demand refresh |
| **`python3 shell_core/scripts/dr_sync.py <target>`** | Run one or more specific targets |

The startup event is the primary trigger because most populator sources
(routers, code modules) require an API restart to take effect anyway.

## Wired sync targets

All 9 typed surfaces have populators. Six are auto-derived from real state;
three are curated lists in `dr_sync.py` (the script itself is the source-of-truth).

| Target | Source | Populates |
|---|---|---|
| `apis` | FastAPI `app.openapi()` + router files' module docstrings | `dr_router`, `dr_api` |
| `deps` | `shell_core/ui/package.json` + `node_modules/*/package.json#description` (npm); `importlib.metadata` in running venv (pip) | `dr_dependencies` |
| `services` | `ecosystem.config.cjs` — convention: each app has `summary` field (pm2 ignores extra keys) | `dr_services` |
| `libs` | `shell_core/api/common/*.py` module docstrings (backend); `shell_core/ui/src/lib/*.js` first `//` comment (frontend) | `dr_lib` |
| `repos` | `git remote get-url origin` + `gh repo view --json description,name` | `dr_repo` |
| `filepaths` | Curated `_FILEPATH_ENTRIES` list in `dr_sync.py` | `dr_filepath` |
| `automations` | Curated `_AUTOMATION_ENTRIES` list in `dr_sync.py` | `dr_automations` |
| `env` | Curated `_ENV_ENTRIES` list in `dr_sync.py` (no values stored, registry only) | `dr_env` |

## When you modify something

| You modified... | What to do |
|---|---|
| A route handler | `api-design` — keep `summary=` ≤100 chars in sync with behavior. Restart API or `make db-sync` to refresh. |
| A router file | `api-design` — keep module docstring + `tags=` fresh. |
| `package.json` (UI) | Auto — pulled from `description` field. |
| `pip install <X>` (substrate) | Auto — pulled from package metadata. |
| `ecosystem.config.cjs` | Update the `summary` field on the affected app. |
| `api/common/*.py` | Keep module docstring fresh — first line is the lib summary. |
| `ui/src/lib/*.js` | Keep first `//` comment fresh. |
| Adding a notable file/dir | Add to `_FILEPATH_ENTRIES` in `dr_sync.py`. |
| Adding cron/pm2/startup automation | Add to `_AUTOMATION_ENTRIES` in `dr_sync.py`. |
| New env var the substrate uses | Add to `_ENV_ENTRIES` in `dr_sync.py`. |

## Adding a new sync target

1. Pick a stable identity column for the typed table (e.g. `(project, name)` for `dr_dependencies`).
2. Write `sync_<target>(conn, app=None)` in `shell_core/scripts/dr_sync.py`. Idempotent UPSERT keyed on the identity column. Return `{"<surface>": {"insert": N, "update": N}}`.
3. Register in `SYNCS` dict.
4. The startup hook and `make db-sync` pick it up automatically via `sync_all`.

## Pre-modification check

Before changing anything that's catalogued, query the catalogue first:

```sql
-- substrate-wide
SELECT * FROM v_dr_catalogue WHERE ref_table = 'dr_<surface>' AND name LIKE '%<target>%';

-- this shell's bindings
SELECT * FROM v_shell_catalogue WHERE shell_id = <self> AND ref_table = 'dr_<surface>';
```

If a row exists, update its source. If not, after the modification trigger
sync (`make db-sync`) or wait for the next restart-driven sync. Never
manually INSERT into a typed table — it'll diverge from source-of-truth
on the next sync.
