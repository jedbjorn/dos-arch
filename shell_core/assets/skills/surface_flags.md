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

`GET /flags` returns every flag in the substrate, each with its schedule
fields. Fetch, then keep only this shell's open ones:

```bash
curl -fsS -H "Authorization: Bearer $DOS_API_TOKEN" "$DOS_API_URL/flags" \
  | python3 -c "
import sys, json
SHELL_ID = <self>          # your shell_id — see ## ACTIVE SESSION
prio = {'High': 1, 'Medium': 2, 'Low': 3}
rows = [f for f in json.load(sys.stdin)
        if f['shell_id'] == SHELL_ID and f['resolved'] == 0]
rows.sort(key=lambda f: (prio.get(f['priority'], 4),
                         f['effective_start'] or '9999', f['flag_id']))
for f in rows:
    print(f)
"
```

Output:

**Open Flags** — columns: ID | Priority | Status | Description | Effective Start | Effective End | Parent
- Status is `schedule_status` (`scheduled` / `in_progress` / `unscheduled`).
- Effective Start/End come from the flag-schedule view (`parent_flag_id`
  chain + `start_date` override + `estimated_days`).
- Sort: High → Medium → Low, then effective_start ascending.
- If none: state "No open flags."
