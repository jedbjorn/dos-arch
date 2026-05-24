---
name: file_find
description: Find files by name using glob semantics.
kind: builtin
handler: file.find
---
<!-- @@ SPEC @@ -->
{
  "type": "object",
  "properties": {
    "name_pattern": {
      "type": "string",
      "description": "glob pattern, e.g. *.py"
    },
    "path": {
      "type": "string",
      "description": "directory to search under, defaults to the working dir"
    }
  },
  "required": [
    "name_pattern"
  ]
}

<!-- @@ PROMPT @@ -->
### file_find — find files by name (glob)

**use when:** locating files whose names match a pattern, without caring about contents. For content search, use `file_search`.

**args (model fills):**
- `name_pattern` (string, required) — glob pattern, e.g. `*.py`.
- `path` (string, optional) — directory to search under. Defaults to the working directory.

**example:** find every Python file under a directory

  <tool:file_find>{"name_pattern":"*.py","path":"~/dos-arch/shell_core"}</tool>
