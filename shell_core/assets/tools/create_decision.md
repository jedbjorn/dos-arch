---
name: create_decision
description: Record a major decision (canonical row in shell_decisions). shell_id is filled from the calling shell's Bearer token — the model only supplies content.
kind: builtin
handler: decision.create
---
<!-- @@ SPEC @@ -->
{
  "type": "object",
  "properties": {
    "decision":           { "type": "string", "description": "What was decided. One tight sentence." },
    "rationale":          { "type": "string", "description": "Why — the context that makes the decision make sense later." },
    "priority":           { "type": "string", "enum": ["M"], "description": "Major decisions only. Defaults to 'M'." },
    "decision_date":      { "type": "string", "description": "ISO date (YYYY-MM-DD). Defaults to today." },
    "parent_decision_id": { "type": "integer", "description": "Existing decision this one supersedes." }
  },
  "required": ["decision", "rationale"]
}

<!-- @@ PROMPT @@ -->
### create_decision — record a major decision

**use when:** a Major (M-level) decision has been made and needs to land in the canonical decision log. Includes project-architectural decisions made while working in a code repo — repo ADR files are mirrors, not substitutes. Append-only; supersede by linking via `parent_decision_id`, never edit prior rows.

**args (model fills — shell_id is set from the Bearer token):**
- `decision` (string, required) — what was decided. One tight sentence.
- `rationale` (string, required) — why; the context that makes it make sense later.
- `priority` (string, optional) — currently only `M` (Major). Defaults to `M`.
- `decision_date` (string, optional) — ISO `YYYY-MM-DD`. Defaults to today.
- `parent_decision_id` (integer, optional) — id of the decision this one supersedes.

**example:** record an architectural decision

  <tool:create_decision>{"decision":"Tool prompts move from catalog_universal into per-tool prompt_block","rationale":"Local 8B can't form a real call from name+desc. Each tool now carries its own block — name, when-to-use, args, example."}</tool>
