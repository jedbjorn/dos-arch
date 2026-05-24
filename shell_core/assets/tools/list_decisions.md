---
name: list_decisions
description: List this shell's decisions, with optional filters. shell_id from Bearer.
kind: builtin
handler: decision.list
---
<!-- @@ SPEC @@ -->
{
  "type": "object",
  "properties": {
    "q": {
      "type": "string",
      "description": "Substring match against decision text or rationale."
    },
    "priority": {
      "type": "string",
      "description": "Filter by priority. Currently only 'M'."
    },
    "date_from": {
      "type": "string",
      "description": "ISO date (YYYY-MM-DD). Decisions on or after."
    },
    "date_to": {
      "type": "string",
      "description": "ISO date (YYYY-MM-DD). Decisions on or before."
    }
  },
  "required": []
}

<!-- @@ PROMPT @@ -->
### list_decisions — list this shell's decisions

**use when:** reviewing prior decisions — searching the rationale log, scoping by date, or scanning recent context before a new write. Decisions are append-only; this is the read side.

**args (model fills — shell_id is implicit from the Bearer token):**
- `q` (string, optional) — substring match against decision text or rationale.
- `priority` (string, optional) — filter by priority. Currently only `M`.
- `date_from` (string, optional) — ISO `YYYY-MM-DD`; inclusive lower bound.
- `date_to` (string, optional) — ISO `YYYY-MM-DD`; inclusive upper bound.

**example:** search recent decisions for a keyword

  <tool:list_decisions>{"q":"prompt_block","date_from":"2026-05-01"}</tool>
