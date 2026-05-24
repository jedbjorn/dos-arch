---
name: proc_list
description: List running processes, optionally name-filtered.
kind: builtin
handler: proc.list
---
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
