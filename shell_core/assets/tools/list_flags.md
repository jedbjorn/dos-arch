---
name: list_flags
description: List this shell's flags. shell_id is filled from the Bearer token; the model only narrows by optional filters.
kind: builtin
handler: flag.list
---
<!-- @@ SPEC @@ -->
{
  "type": "object",
  "properties": {},
  "required": []
}

<!-- @@ PROMPT @@ -->
### list_flags — list this shell's flags

**use when:** surfacing this shell's flags — open, resolved, or tracking — for triage. The OPEN FLAGS prompt pointer carries only the count; this tool reads the rows.

**args (model fills — shell_id is implicit from the Bearer token):**
- *(none required — defaults to all flags for this shell)*

**example:** list this shell's flags

  <tool:list_flags>{}</tool>
