---
name: create_decision
description: Record a Major (M) decision for the calling shell — the canonical decision record. shell_id is set server-side from the bearer token; supply content only. WHEN — a Major architectural or directional choice is made, including project-architectural decisions made while working in a code repo; repo ADR files (DECISIONS.md, docs/decisions/) are mirrors, not substitutes for this record. SCOPE — records one decision; listing or superseding existing decisions is a separate write. CONVENTION — 'decision' is the choice in one line; 'rationale' is the why and context; decision_date defaults to today.
kind: builtin
handler: decision.create
---
{
  "type": "object",
  "required": ["decision"],
  "properties": {
    "decision": {
      "type": "string",
      "minLength": 10,
      "description": "Decision. Required. The choice made, stated in one clear line (~40-160 characters). E.g. 'Purpose-built tools ride with their owning skill, never global'. Derived from what was just decided in the conversation."
    },
    "rationale": {
      "type": "string",
      "description": "Rationale. Not Required but strongly preferred. The why — context, trade-offs, what it unblocks or supersedes. The record is durable; capture enough that future-you need not re-read the chat to act on it."
    },
    "decision_date": {
      "type": "string",
      "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
      "description": "Decision date. Not Required. ISO date (YYYY-MM-DD). Defaults to today if omitted. Set only when recording a decision from a known past date."
    },
    "parent_decision_id": {
      "type": "integer",
      "description": "Parent decision ID. Not Required. decision_id of the decision this one supersedes. Set only when explicitly replacing a prior decision."
    }
  }
}
