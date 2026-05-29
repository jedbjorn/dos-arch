---
name: surface_catalogue
description: Surface the substrate catalogue (dr_*) on demand — routes, routers, deps, libs, services, repos, files, automations, env. Query it before grepping the codebase.
category: workflow
common: 0
---
# surface_catalogue

A live index of what exists in the substrate. Query it before grepping —
one call beats many `find` / `grep` / `Read` calls.

`$DOS_API_URL` and `$DOS_API_TOKEN` are in your container environment.

```bash
# everything
curl -fsS -H "Authorization: Bearer $DOS_API_TOKEN" "$DOS_API_URL/catalogue"

# one surface — table is a ref_table: dr_api, dr_router, dr_services,
# dr_filepath, dr_env, dr_repo, dr_lib, dr_dependencies, dr_automations
curl -fsS -H "Authorization: Bearer $DOS_API_TOKEN" "$DOS_API_URL/catalogue?table=dr_api"

# substring search across name + description
curl -fsS -H "Authorization: Bearer $DOS_API_TOKEN" "$DOS_API_URL/catalogue?q=flag"
```

Each row is `{ref_table, ref_id, name, description_short}`. Group the
output by `ref_table` when you present it.

## When to use

- Cold start — orienting in an unfamiliar substrate.
- "Where does X live?" — `?q=<X>`.
- "Is there an API for Y?" — `?table=dr_api&q=<Y>`.
- "What auto-runs / what env vars matter?" — `?table=dr_automations`,
  `?table=dr_env`.

The catalogue auto-syncs on every API restart. See `catalogue_sync` for the
sync pipeline.
