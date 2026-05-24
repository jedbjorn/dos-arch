---
name: file_edit
description: Replace a unique string in an existing file.
kind: builtin
handler: file.edit
---
{
  "type": "object",
  "properties": {
    "path": {
      "type": "string",
      "description": "file to edit"
    },
    "old_str": {
      "type": "string",
      "description": "exact text to replace, must occur exactly once"
    },
    "new_str": {
      "type": "string",
      "description": "replacement text"
    }
  },
  "required": [
    "path",
    "old_str",
    "new_str"
  ]
}
