---
name: surface_flags
description: Surface open flags for this shell on demand.
category: workflow
common: 1
command: --flags
---
# surface_flags

Surface open flags for this shell. Run on demand with `--flags`.

Replace `<YOUR_SHELL_ID>` with your shell_id from the ACTIVE SESSION block.

```python
import sqlite3
SHELL_ID = <YOUR_SHELL_ID>
conn = sqlite3.connect('shell_db.db')
cur = conn.cursor()
cur.execute('''
    SELECT f.flag_id, f.display_name, f.priority, f.description,
           f.start_date, f.estimated_days, f.parent_flag_id,
           fs.effective_start, fs.effective_end, fs.status AS schedule_status
    FROM flags f
    LEFT JOIN flag_schedule fs ON fs.flag_id = f.flag_id
    WHERE f.shell_id = ? AND f.resolved = 0 AND f.is_deleted = 0
    ORDER BY CASE f.priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 WHEN 'Low' THEN 3 ELSE 4 END,
             fs.effective_start ASC NULLS LAST,
             f.flag_id ASC
''', (SHELL_ID,))
rows = cur.fetchall()
conn.close()
```

Output:

**Open Flags** — columns: ID | Priority | Status | Description | Effective Start | Effective End | Parent
- Status comes from `flag_schedule.status` (`scheduled` / `in_progress` / `unscheduled`).
- Effective Start/End come from the `flag_schedule` recursive view (`parent_flag_id` chain + `start_date` override + `estimated_days`).
- Sort: High → Medium → Low, then by effective_start ascending.
- If none: state "No open flags."
