---
name: blueprint
description: Turn a one-line objective into a step-by-step construction plan for multi-session, multi-agent engineering projects. Adversarial review gate, dependency graph, parallel step detection.
category: workflow
common: 0
---
# blueprint

- **skill_id:** 21
- **category:** workflow
- **common:** 0
- **description:** Turn a one-line objective into a step-by-step construction plan for multi-session, multi-agent engineering projects. Adversarial review gate, dependency graph, parallel step detection.

---

## Blueprint — Construction Plan Generator

**Dev_Ref discipline:** Pre-change check `dr_*` (shell_db.db) for current state. Post-change write `dr_log` row (≤50 char summary, session_id).

**Trigger:** User requests a plan, blueprint, or roadmap for a complex multi-session task, or describes work that spans multiple PRs/sessions.
**Do not trigger** for tasks completable in a single session or fewer than 3 tool calls, or when the user says "just do it".

---

### Phase 1: Research

- Check git status, existing open flags, and current_state in DB
- Query existing plans:
  ```python
  import sqlite3
  conn = sqlite3.connect('shell_core/shell_db.db')
  c = conn.cursor()
  c.execute("SELECT plan_id, project, title, status, created_at FROM plans WHERE shell_id=2 ORDER BY created_at DESC LIMIT 10")
  for r in c.fetchall(): print(r)
  ```
- Read relevant project files to understand current state
- Identify what already exists vs. what needs building

---

### Phase 2: Design

Break the objective into one-session-sized steps (3–12 typical):
- Assign dependency order (what must complete before what)
- Identify steps that can run in parallel (no shared file/output dependencies)
- Assign model tier per step: strongest (Opus) for architecture/design, default (Sonnet) for implementation
- Define rollback strategy per step

---

### Phase 3: Draft

Write a self-contained plan. Every step must include:
- Context brief (what a fresh session needs to know to execute this step cold)
- Task list
- Verification commands or exit criteria
- Rollback if applicable

Present the full draft to the user for review before saving.

---

### Phase 4: Adversarial Review

Delegate to a strongest-model sub-agent for review against:
- Are all steps necessary and non-redundant?
- Are dependency edges correct?
- Are any steps missing that would cause failure?
- Are verification criteria testable?
- Anti-patterns: over-engineering, missing rollback, steps too large to execute in one session

Fix all critical findings before saving.

---

### Phase 5: Save to DB

After user approves:

```python
import sqlite3
conn = sqlite3.connect('shell_core/shell_db.db')
c = conn.cursor()
c.execute("PRAGMA foreign_keys=ON")
c.execute("""
    INSERT INTO plans (shell_id, project, title, objective, content, status, step_count)
    VALUES (2, ?, ?, ?, ?, 'active', ?)
""", (project, title, objective, full_plan_content, step_count))
conn.commit()
print("plan_id:", c.lastrowid)
conn.close()
```

Confirm plan_id to user. No flat files written.

---

### Plan Mutation

If steps need to change mid-execution:
```python
# Update status or content
c.execute("UPDATE plans SET status=?, content=? WHERE plan_id=?", (new_status, updated_content, plan_id))
```

Valid status transitions: `draft` → `active` → `complete` | `abandoned`

---

### Querying Plans

```python
# All active plans
c.execute("SELECT plan_id, project, title, step_count, created_at FROM plans WHERE shell_id=2 AND status='active'")

# Full plan content
c.execute("SELECT content FROM plans WHERE plan_id=?", (plan_id,))
```

