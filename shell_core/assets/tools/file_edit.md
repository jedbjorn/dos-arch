---
name: file_edit
description: Replace a unique string in an existing file.
kind: builtin
handler: file.edit
---
<!-- @@ SPEC @@ -->
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

<!-- @@ PROMPT @@ -->
### file_edit — replace a unique string in a file

**use when:** changing a specific span in an existing file. `old_str` must match exactly once — include enough surrounding context to make it unique. For a multi-edit pass, repeat the call.

**args (model fills):**
- `path` (string, required) — file to edit.
- `old_str` (string, required) — exact text to replace; must occur exactly once.
- `new_str` (string, required) — replacement text.

**example:** rename a function call

  <tool:file_edit>{"path":"src/api.py","old_str":"open_flag(","new_str":"create_flag("}</tool>
