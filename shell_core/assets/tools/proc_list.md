---
name: proc_list
description: List running processes, optionally name-filtered.
kind: builtin
handler: proc.list
---
<!-- @@ SPEC @@ -->
{
  "type": "object",
  "properties": {
    "name_filter": {
      "type": "string",
      "description": "optional substring to match against process names"
    }
  },
  "required": []
}

<!-- @@ PROMPT @@ -->
### proc_list — list running processes

**use when:** checking what is running on the host, optionally filtered by name substring.

**args (model fills):**
- `name_filter` (string, optional) — case-sensitive substring matched against process names. Omit for everything.

**example:** find any python process

  <tool:proc_list>{"name_filter":"python"}</tool>
