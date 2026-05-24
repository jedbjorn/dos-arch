---
name: file_append
description: Append content to the end of an existing file.
kind: builtin
handler: file.append
---
<!-- @@ SPEC @@ -->
{
  "type": "object",
  "properties": {
    "path": {
      "type": "string",
      "description": "file to append to"
    },
    "content": {
      "type": "string",
      "description": "text to append"
    }
  },
  "required": [
    "path",
    "content"
  ]
}

<!-- @@ PROMPT @@ -->
### file_append — append to a file

**use when:** adding to the tail of an existing file (a log, a running document). The file must already exist — use `file_write` to create one.

**args (model fills):**
- `path` (string, required) — existing file path.
- `content` (string, required) — text to append. Include any leading newline you need.

**example:** append a line to a log

  <tool:file_append>{"path":"~/scratch/notes.log","content":"\n[2026-05-24] another entry\n"}</tool>
