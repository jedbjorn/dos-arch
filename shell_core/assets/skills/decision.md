---
name: decision
description: --decision [decision] [context] — Record a Major decision: INSERT row to shell_decisions (canonical) and append to active session narrative. Includes project-architectural decisions made in a code repo — repo ADR files are mirrors, not substitutes.
category: workflow
common: 1
---
**API-ONLY** — This skill uses the API ONLY. If you are unable to reach any needed API endpoint: surface to FnB Partner in chat AND send a message to DosDev (shell_id=2) via POST /shell-messages.

---

# decision

- **Trigger:** `--decision`
- **Args:** `[decision] [context]` — interviewed if not provided inline

Record a major decision with context. Writes a row to `shell_decisions` and appends a line to the active arc narrative.

---

## Scope

Applies to **Major decisions** (M priority), including project-architectural decisions made while working in a code repo. Repo-facing ADR files (`DECISIONS.md`, `docs/decisions/`) are mirrors for the repo's audience — they do **not** substitute for the `shell_decisions` row. The DB row is canonical; repo files link to it, never the reverse.

---

## Steps

1. **Resolve args.** If decision or context were not provided inline, interview:
   - "What is the decision?"
   - "What is the context — why does this matter?"
   Wait for each answer before continuing. Never guess.

2. **Insert decision** via POST /shells/{SHELL_ID}/decisions:
   ```bash
   curl -s -X POST https://localhost:8000/shells/{SHELL_ID}/decisions \
     -H "X-API-Key: {AUTH_KEY}" \
     -H "Content-Type: application/json" \
     -d '{"decision_date": "YYYY-MM-DD", "priority": "M", "decision": "{decision}", "rationale": "{context}"}'
   ```
   Use today's date. Check for 200. On non-200: surface error to FnB, message DosDev, stop.

3. **Append to active arc narrative** via PATCH /shell-memory-archives/{ACTIVE_ARCHIVE_ID}:
   ```bash
   curl -s -X PATCH https://localhost:8000/shell-memory-archives/{ACTIVE_ARCHIVE_ID} \
     -H "X-API-Key: {AUTH_KEY}" \
     -H "Content-Type: application/json" \
     -d '{"narrative_entry": "[HH:MM] DECISION: {decision} — {context}"}'
   ```
   Check for 200. On non-200: surface error to FnB, message DosDev, stop.

4. **Confirm:** "Decision recorded."

---

## Placeholders

| Placeholder | Source |
|---|---|
| `{SHELL_ID}` | Shell identity — known at session start |
| `{AUTH_KEY}` | `shells.auth_key` — loaded at session start |
| `{ACTIVE_ARCHIVE_ID}` | `shells.active_archive_id` — set at session start |

---

## Idempotent?

No. Each invocation inserts a new `shell_decisions` row. If fired twice with the same decision, two identical rows are written (different `decision_id`s). FnB should verify before triggering.
