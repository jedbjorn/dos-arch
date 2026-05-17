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
in your system prompt). `$DOS_API_URL` and `$DOS_API_TOKEN` are in your
container environment; `<self>` is your shell_id, in `## ACTIVE SESSION` of
your CLAUDE.md.

`resolved` is tri-state: `0` = Open, `1` = Resolved, `2` = Tracking.
Unresolved work is **`0` and `2`** — Open flags are active blockers;
Tracking flags are real but not yet effective (future-scheduled). Resolved
(`1`) flags are done and not surfaced.

`GET /flags` returns every flag in the substrate, each with its schedule
fields. Fetch, then keep only this shell's unresolved ones:

```bash
curl -fsS -H "Authorization: Bearer $DOS_API_TOKEN" "$DOS_API_URL/flags" \
  | python3 -c "
import sys, json
SHELL_ID = <self>          # your shell_id — see ## ACTIVE SESSION
prio = {'High': 1, 'Medium': 2, 'Low': 3}
rows = [f for f in json.load(sys.stdin)
        if f['shell_id'] == SHELL_ID and f['resolved'] in (0, 2)]
rows.sort(key=lambda f: (f['resolved'],                 # Open before Tracking
                         prio.get(f['priority'], 4),
                         f['effective_start'] or '9999', f['flag_id']))
for f in rows:
    print(f)
"
```

Output — two groups, Open first:

**Open Flags** (`resolved == 0`) — active blockers. Columns: ID | Priority | Status | Description | Effective Start | Effective End | Parent

**Tracking** (`resolved == 2`) — real but not yet effective; list below the Open group, same columns.

- Status is `schedule_status` (`scheduled` / `in_progress` / `unscheduled`).
- Effective Start/End come from the flag-schedule view (`parent_flag_id`
  chain + `start_date` override + `estimated_days`).
- Sort within each group: High → Medium → Low, then effective_start ascending.
- If both groups empty: state "No open or tracking flags."
