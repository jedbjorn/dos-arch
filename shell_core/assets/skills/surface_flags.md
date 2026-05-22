---
name: surface_flags
description: Surface open flags for this shell on demand.
category: workflow
common: 1
command: --flags
---
# surface_flags

Surface this shell's open flags. Run on demand with `--flags`.

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
