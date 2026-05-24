---
name: create_flag
description: Open a new flag (work tracker / blocker). shell_id is filled from the calling shell's Bearer token — the model only supplies content.
kind: builtin
handler: flag.create
---
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
