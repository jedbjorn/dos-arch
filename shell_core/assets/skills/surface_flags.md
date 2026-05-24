---
name: surface_flags
description: Surface open flags for this shell on demand.
category: workflow
common: 1
command: --flags
---
# surface_flags

Surface this shell's open flags. Run on demand with `--flags`.

The fetch is the `list_flags` tool — see its block in the `## TOOLS ##`
section of your boot prompt. shell_id is resolved server-side from the
Bearer token, so the call is `<tool:list_flags>{}</tool>`.

`resolved` is tri-state: `0` = Open, `1` = Resolved, `2` = Tracking.
Unresolved work is **`0` and `2`** — Open flags are active blockers;
Tracking flags are real but not yet effective (future-scheduled). Resolved
(`1`) flags are done and not surfaced.

## Steps

1. **Fetch** — call `list_flags`. The endpoint scopes server-side to this
   shell; the response carries each row's schedule fields.
2. **Filter** — keep only rows where `resolved` is `0` or `2`. Drop the
   rest.
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
