---
name: file_list
description: List the entries of a directory.
kind: builtin
handler: file.list
---
<!-- @@ SPEC @@ -->
{
  "type": "object",
  "properties": {
    "path": {
      "type": "string",
      "description": "directory path"
    },
    "recursive": {
      "type": "boolean",
      "description": "recurse into subdirectories"
    }
  },
  "required": [
    "path"
  ]
}

<!-- @@ PROMPT @@ -->
### file_list — list directory entries

**use when:** seeing what is in a directory. Set `recursive` for a full tree; otherwise just the immediate entries.

**args (model fills):**
- `path` (string, required) — directory path.
- `recursive` (boolean, optional) — recurse into subdirectories. Default false.

**example:** list a directory shallowly

  <tool:file_list>{"path":"~/dos-arch/shell_core/assets/tools"}</tool>
