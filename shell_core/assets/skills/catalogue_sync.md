---
name: catalogue_sync
description: How the dr_* catalogue is populated and kept in sync — the 9 typed surfaces, the populator, and how to extend it. Substrate-maintenance, admin shell.
category: workflow
common: 0
---
# catalogue_sync

The catalogue (`dr_*` tables → `v_dr_catalogue`) is a live index of the
substrate's components — routes, routers, deps, libs, services, repos,
files, automations, env vars. Source of truth is always the underlying
state (code/config); the catalogue is a projection of it.

*Reading* the catalogue is the `surface_catalogue` skill (`GET /catalogue`).
This skill is *maintaining* it — admin work, with the repo at `/substrate`.

## Populator

`/substrate/shell_core/scripts/dr_sync.py` populates all 9 surfaces via
`sync_all`. It runs:

- **on every API restart** — the primary trigger; a recompose re-syncs;
- **`make db-sync`** — explicit, host-side;
- **`python3 dr_sync.py <target>`** — one surface, for debugging.

## The 9 surfaces

Six auto-derive from real state; three are curated lists inside `dr_sync.py`:

| Auto-derived | Source |
|---|---|
| `dr_router`, `dr_api` | FastAPI routes + router-module docstrings |
| `dr_dependencies` | `package.json` + installed pip metadata |
| `dr_lib` | backend module docstrings / UI lib first-comment |
| `dr_services` | `ecosystem.config.cjs` `summary` fields |
| `dr_repo` | `git remote` + `gh repo view` |

| Curated in `dr_sync.py` | List |
|---|---|
| `dr_filepath` | `_FILEPATH_ENTRIES` |
| `dr_automations` | `_AUTOMATION_ENTRIES` |
| `dr_env` | `_ENV_ENTRIES` |

## When you change something catalogued

| Changed | Keep in sync |
|---|---|
| a route / router | the `summary=` and the router-module docstring |
| `ecosystem.config.cjs` | the app's `summary` field |
| a backend / UI lib | the module docstring / first `//` comment |
| a notable file, automation, or env var | the matching `_*_ENTRIES` list in `/substrate/shell_core/scripts/dr_sync.py` |

It re-syncs at the next recompose (`./install/api-up.sh`), or run
`make db-sync` host-side. Never hand-write a `dr_*` row — the next sync
overwrites it from source.

## Adding a sync target

1. Pick a stable identity column for the typed table.
2. Write `sync_<target>(conn, app=None)` in `dr_sync.py` — an idempotent
   UPSERT keyed on that column; return
   `{"<surface>": {"insert": N, "update": N}}`.
3. Register it in the `SYNCS` dict — `sync_all` and `make db-sync` pick it
   up automatically.
