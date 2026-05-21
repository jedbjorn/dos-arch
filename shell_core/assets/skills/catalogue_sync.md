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
`sync_all`. It runs in two places, and the split matters:

- **host-side — the complete sync.** `./install/api-up.sh` (step [4/6],
  every recompose), `make db-sync`, and a daily cron (see *Run log +
  monitoring*). `dr_repo` needs `git` + the repo's `.git`; `dr_services`
  needs `node` + `ecosystem.config.cjs` — both only populate here, where
  the host has the tooling and the whole repo.
- **in-container, on every API startup — best-effort refresh.** The
  `dos-api` image is `python:3.12-slim` with no `git`/`node` and mounts
  only `shell_core`, so the repo + services surfaces silently no-op
  there (idempotent — they never clobber the host-synced rows).
  `dr_router`/`dr_api`/`dr_dependencies` refresh fine in-container.
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
| a **core** memory endpoint (shell state, flags, seed/L&S, decisions) | also the `MEMORY_PROTOCOL` block in `shell_core/templates/catalog_universal.md`, in the same PR |
| `ecosystem.config.cjs` | the app's `summary` field |
| a backend / UI lib | the module docstring / first `//` comment |
| a notable file, automation, or env var | the matching `_*_ENTRIES` list in `/substrate/shell_core/scripts/dr_sync.py` |

It re-syncs at the next recompose (`./install/api-up.sh`), or run
`make db-sync` host-side. Never hand-write a `dr_*` row — the next sync
overwrites it from source.

The core memory-endpoint map in the boot system prompt is **hand-maintained
prose**, not auto-synced from `dr_api` — it carries when/why semantics the
catalogue's `description_short` can't. That surface is stable contract, but
still maturing (e.g. the projects write surface is a known gap). Whoever adds
or moves a core endpoint owns the template edit; nothing catches that drift
automatically.

## Run log + monitoring

Every `sync_all` invocation writes one row to `dr_sync_runs` — `trigger_kind`
is `cron`, `startup`, or `manual`. Each row carries the per-surface counts as
JSON, `total_insert`/`total_update`, `had_error`, and a 100-char `error`.
Rolling-100 retention via trigger. It's the audit trail for catalogue drift.

The only *automatic* full sync is a host-side cron — `daily 04:00`, installed
once via `./install/cron-install.sh`. Nothing else refreshes
`dr_repo`/`dr_services` on its own; without the cron they drift stale between
recomposes.

Monitor via `GET /admin/catalogue-sync` (admin-gated): recent runs,
`last_cron`, `recent_errors`, and `stale` — true when no cron run landed in
the last 26h. A run that never started leaves no row at all, so `stale` is
the cron-didn't-fire signal. Watching this is the admin shell's job.

## Adding a sync target

1. Pick a stable identity column for the typed table.
2. Write `sync_<target>(conn, app=None)` in `dr_sync.py` — an idempotent
   UPSERT keyed on that column; return
   `{"<surface>": {"insert": N, "update": N}}`.
3. Register it in the `SYNCS` dict — `sync_all` and `make db-sync` pick it
   up automatically.
