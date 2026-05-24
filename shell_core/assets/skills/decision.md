---
name: decision
description: --decision [decision] [context] — Record a Major decision via the substrate API and append it to the active session narrative. Includes project-architectural decisions made in a code repo — repo ADR files are mirrors, not substitutes.
category: workflow
common: 1
---

# decision

- **Trigger:** `--decision`
- **Args:** `[decision] [context]` — interviewed if not provided inline

Record a major decision with context: a decision record (canonical) plus
a line on the active session narrative.

The work is two named tools — see their blocks in the `## TOOLS ##`
section of your boot prompt:

- `create_decision` writes the canonical row to `shell_decisions`.
- `append_narrative` adds the decision line to the active session
  narrative.

Both resolve `shell_id` (and `archive_id`, for narrative) server-side
from the Bearer token, so you fill only the content.

## Scope

Applies to **Major decisions** (M priority), including project-
architectural decisions made while working in a code repo. Repo-facing
ADR files (`DECISIONS.md`, `docs/decisions/`) are mirrors for the repo's
audience — they do **not** substitute for the decision record. The API
record is canonical; repo files link to it, never the reverse.

## Steps

1. **Resolve args.** If `decision` or `context` were not provided
   inline, interview — "What is the decision?", "What is the context —
   why does this matter?" Wait for each answer. Never guess.
2. **Record the decision** — call `create_decision` with
   `{"decision": "...", "rationale": "..."}`. On error, surface and stop.
3. **Append to the narrative** — call `append_narrative` with
   `{"narrative_entry": "[HH:MM] DECISION: {decision} — {context}"}`.
   A 409 here means the shell has no active archive — surface that gap
   to the operator and stop; the decision row from step 2 stays
   canonical regardless.
4. **Confirm:** "Decision recorded."

## Idempotent?

No. Each invocation records a new decision. Verify before triggering.
