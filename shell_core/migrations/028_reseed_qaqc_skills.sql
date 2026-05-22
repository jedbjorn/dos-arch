-- 028 — re-seed db_patch + surface_flags skill content.
--
-- PR #79 rewrote these two skills from a shell/exec idiom (grep / curl /
-- python3) to the tool idiom (file_search / file_read / file_edit / api_get)
-- so they run on the exec-less Sys-Admin shell. That PR changed only the
-- asset *.md files — the fresh-install seed path. seed_from_assets is
-- INSERT-missing-only, so an already-bootstrapped DB kept the stale content.
--
-- This migration carries the same rewrite to existing DBs: the content below
-- is the verbatim markdown body of assets/skills/{db_patch,surface_flags}.md.
-- Frontmatter (name / description / category / common) was unchanged by #79,
-- so only `content` is updated.
--
-- Plain SQL: migrate.py owns the transaction and the schema_migrations row.


UPDATE skills SET content = '# db_patch

Patch a bug in the substrate API''s source code — a wrong SQL query, a
missing Pydantic field, a malformed response. Substrate-maintenance work;
runs from an admin shell (Sys-Admin), which has the repo bind-mounted at
`/substrate`.

> Editing API source needs the `/substrate` mount. If it is not present,
> this shell is not admin-provisioned — surface that to the operator.

---

## 1. Locate

The API is `/substrate/shell_core/api/` — `main.py` (app + middleware) and
`routers/*.py` (the endpoints). Use `file_search` over
`/substrate/shell_core/api/routers/` for the route''s decorator
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
fix every instance in one pass. Don''t patch one endpoint and leave its
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
> I''ll re-verify."

After the recompose: repeat step 2 to confirm the fix, and send a partial
`api_patch` to each sibling touched to confirm no regression.
' WHERE name = 'db_patch';

UPDATE skills SET content = '# surface_flags

Surface this shell''s open flags. Run on demand with `--flags`.

Memory is read over the substrate API — no DB file (see MEMORY ARCHITECTURE
in your system prompt). `<self>` is your shell_id, in `## ACTIVE SESSION` of
your CLAUDE.md.

`resolved` is tri-state: `0` = Open, `1` = Resolved, `2` = Tracking.
Unresolved work is **`0` and `2`** — Open flags are active blockers;
Tracking flags are real but not yet effective (future-scheduled). Resolved
(`1`) flags are done and not surfaced.

## Steps

1. **Fetch** — `api_get` on `/flags`. It returns every flag in the
   substrate, each with its schedule fields.
2. **Filter** — keep only rows where `shell_id` is `<self>` **and**
   `resolved` is `0` or `2`. Drop the rest.
3. **Sort** the kept rows: `resolved` ascending (Open `0` before Tracking
   `2`), then priority High → Medium → Low, then `effective_start`
   ascending (nulls last), then `flag_id`.

## Output — two groups, Open first

**Open Flags** (`resolved == 0`) — active blockers. Columns: ID | Priority | Status | Description | Effective Start | Effective End | Parent

**Tracking** (`resolved == 2`) — real but not yet effective; list below the Open group, same columns.

- Status is `schedule_status` (`scheduled` / `in_progress` / `unscheduled`).
- Effective Start/End come from the flag-schedule view (`parent_flag_id`
  chain + `start_date` override + `estimated_days`).
- If both groups empty: state "No open or tracking flags."
' WHERE name = 'surface_flags';
