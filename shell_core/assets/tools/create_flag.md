---
name: create_flag
description: Open a new flag (work tracker / blocker). shell_id is filled from the calling shell's Bearer token — the model only supplies content.
kind: builtin
handler: flag.create
---
<!-- @@ SPEC @@ -->
{
  "type": "object",
  "properties": {
    "display_name":   { "type": "string", "description": "Short title, e.g. 'CC-077 cron-step hardening'." },
    "description":    { "type": "string", "description": "What the flag tracks. Free-form." },
    "priority":       { "type": "string", "enum": ["High", "Medium", "Low"], "description": "Defaults to 'Medium' if omitted." },
    "start_date":     { "type": "string", "description": "ISO date (YYYY-MM-DD) when work begins. Omit if open now." },
    "parent_flag_id": { "type": "integer", "description": "Existing flag this one is a child of." },
    "estimated_days": { "type": "number", "description": "Rough effort estimate in days." }
  },
  "required": ["display_name"]
}

<!-- @@ PROMPT @@ -->
### create_flag — open a new flag

**use when:** the operator asks to open a flag, or work surfaces a real blocker that needs tracking. CONFIRM with the operator before opening (memory protocol). Resolving an existing flag is a different call.

**args (model fills — shell_id is set from the Bearer token, not by you):**
- `display_name` (string, required) — short title, e.g. `CC-099 docs sweep`.
- `description` (string, optional) — what the flag tracks, why it matters, what unblocks when it closes.
- `priority` (string, optional) — `High` / `Medium` / `Low`. Defaults to `Medium`.
- `start_date` (string, optional) — ISO date `YYYY-MM-DD`. Omit if open now.
- `parent_flag_id` (integer, optional) — existing flag this one is a child of.
- `estimated_days` (number, optional) — rough effort estimate in days.

**example:** open a Medium flag

  <tool:create_flag>{"display_name":"CC-099 docs sweep","description":"Pass over README + skill docs for stale endpoint refs. Blocker for: onboarding doc accuracy."}</tool>
