---
name: file_read
description: Read a file from the working directory.
kind: builtin
handler: file.read
---
<!-- @@ SPEC @@ -->
{
  "type": "object",
  "properties": {
    "path": {
      "type": "string",
      "description": "file path, ~ is expanded"
    },
    "lines": {
      "type": "array",
      "items": {
        "type": "integer"
      },
      "description": "optional [start, end] line numbers, 1-based inclusive"
    }
  },
  "required": [
    "path"
  ]
}

<!-- @@ PROMPT @@ -->
### file_read — read a file

**use when:** opening any file on disk. Prefer a line window when you only need part of a large file.

**args (model fills):**
- `path` (string, required) — file path; `~` is expanded.
- `lines` (array of integers, optional) — `[start, end]`, 1-based inclusive. Omit for the whole file.

**example:** read lines 40–80 of a file

  <tool:file_read>{"path":"~/dos-arch/README.md","lines":[40,80]}</tool>
