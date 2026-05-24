---
name: file_search
description: Search file contents for a pattern.
kind: builtin
handler: file.search
---
<!-- @@ SPEC @@ -->
{
  "type": "object",
  "properties": {
    "pattern": {
      "type": "string",
      "description": "substring, or a regex when regex is true"
    },
    "path": {
      "type": "string",
      "description": "file or directory to search, defaults to the working dir"
    },
    "regex": {
      "type": "boolean",
      "description": "treat pattern as a regular expression"
    }
  },
  "required": [
    "pattern"
  ]
}

<!-- @@ PROMPT @@ -->
### file_search — search file contents

**use when:** finding where a symbol, string, or pattern occurs inside files. For name-only matching, use `file_find`.

**args (model fills):**
- `pattern` (string, required) — substring, or a regular expression when `regex` is true.
- `path` (string, optional) — file or directory to search under. Defaults to the working directory.
- `regex` (boolean, optional) — treat pattern as a regex. Default false (literal substring).

**example:** find a symbol across a tree

  <tool:file_search>{"pattern":"NAMED_API_ROUTES","path":"~/dos-arch/shell_core"}</tool>
