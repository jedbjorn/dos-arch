---
name: decision
description: --decision [decision] [context] — Record a Major decision via the substrate API and append it to the active session narrative. Includes project-architectural decisions made in a code repo — repo ADR files are mirrors, not substitutes.
category: workflow
common: 1
---
**API-ONLY** — this skill writes over the substrate API. If a needed
endpoint is unreachable, surface it to the operator and stop — the API is
extended from the repo, never worked around.

---

# decision

- **Trigger:** `--decision`
- **Args:** `[decision] [context]` — interviewed if not provided inline

Record a major decision with context: a decision record (canonical) plus a
line on the active session narrative.

---

## Scope

Applies to **Major decisions** (M priority), including project-architectural
decisions made while working in a code repo. Repo-facing ADR files
(`DECISIONS.md`, `docs/decisions/`) are mirrors for the repo's audience —
they do **not** substitute for the decision record. The API record is
canonical; repo files link to it, never the reverse.

---

## Steps

`$DOS_API_URL` and `$DOS_API_TOKEN` are in your container environment;
`<self>` is your `shell_id:` and `{archive_id}` is your `archive:` — both
in `## BOOT ##` of your CLAUDE.md.

1. **Resolve args.** If decision or context were not provided inline,
   interview — "What is the decision?", "What is the context — why does this
   matter?" Wait for each answer. Never guess.

2. **Record the decision** — `POST /shells/<self>/decisions`:
   ```bash
   curl -fsS -X POST "$DOS_API_URL/shells/<self>/decisions" \
     -H "Authorization: Bearer $DOS_API_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"decision_date": "YYYY-MM-DD", "priority": "M", "decision": "{decision}", "rationale": "{context}"}'
   ```
   Use today's date. On a non-2xx response: surface the error to the
   operator and stop.

3. **Append to the active session narrative** — `PATCH /shell-memory-archives/{archive_id}`:
   ```bash
   curl -fsS -X PATCH "$DOS_API_URL/shell-memory-archives/{archive_id}" \
     -H "Authorization: Bearer $DOS_API_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"narrative_entry": "[HH:MM] DECISION: {decision} — {context}"}'
   ```
   If `{archive_id}` is `—` (no archive row for this session — common on
   API-model shells, where `shell_memory_archives` is unpopulated), skip
   step 3. The decision record from step 2 is canonical; the narrative
   line is a convenience. On any other non-2xx response: surface the
   error to the operator and stop.

4. **Confirm:** "Decision recorded."

---

## Idempotent?

No. Each invocation records a new decision. Fired twice with the same
decision, two identical records are written. Verify before triggering.
