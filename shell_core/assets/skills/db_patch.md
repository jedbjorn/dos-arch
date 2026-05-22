---
name: db_patch
description: Patch the substrate API's source — SQL queries, Pydantic models, route handlers in shell_core/api/. Locate, reproduce, scan siblings, minimal fix; the change goes live at the next recompose.
category: workflow
common: 0
---
# db_patch

Patch a bug in the substrate API's source code — a wrong SQL query, a
missing Pydantic field, a malformed response. Substrate-maintenance work;
runs from an admin shell (Sys-Admin), which has the repo bind-mounted at
`/substrate`.

> Editing API source needs the `/substrate` mount. If it is not present,
> this shell is not admin-provisioned — surface that to the operator.

---

## 1. Locate

The API is `/substrate/shell_core/api/` — `main.py` (app + middleware) and
`routers/*.py` (the endpoints). Use `file_search` over
`/substrate/shell_core/api/routers/` for the route's decorator
(`@router.get` / `.post` / `.patch` / `.delete`) or its path to find the
handler. `file_read` the handler, its Pydantic model(s), and any SQL
constants it uses.

## 2. Reproduce

Confirm the bug is real before touching code — call the live endpoint with
`api_get` (or `api_post` / `api_patch` / `api_delete` for the verb) and
record exactly what is wrong. If you cannot reproduce it, stop and surface
that to the operator.

## 3. Scan siblings

`file_search` for the same bug pattern across sibling endpoints — a
full-replacement `UPDATE` missing `COALESCE`, a missing model field — and
fix every instance in one pass. Don't patch one endpoint and leave its
siblings broken.

## 4. Patch

`file_edit` the source under `/substrate/shell_core/api/`. Keep it minimal
— only what the bug requires.

## 5. Ship

A container cannot restart the API. The fix goes live when the operator
**recomposes** — `./install/api-up.sh` restarts `dos-api` on the edited
source. Hand off:

> "Patched `<file>` — `<what broke → what was fixed>`; siblings
> `<checked / fixed>`. Recompose (`./install/api-up.sh`) to apply, then
> I'll re-verify."

After the recompose: repeat step 2 to confirm the fix, and send a partial
`api_patch` to each sibling touched to confirm no regression.
