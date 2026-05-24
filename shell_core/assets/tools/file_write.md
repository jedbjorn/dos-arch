---
name: file_write
description: Write a new file. Fails if the path already exists.
kind: builtin
handler: file.write
---
<!-- @@ SPEC @@ -->
{
  "type": "object",
  "properties": {
    "path": {
      "type": "string",
      "description": "file path to create"
    },
    "content": {
      "type": "string",
      "description": "full file content"
    }
  },
  "required": [
    "path",
    "content"
  ]
}

<!-- @@ PROMPT @@ -->
### file_write — create a new file

**use when:** creating a file that does not exist. Fails if the path is already taken — use `file_edit` or `file_append` to change an existing file.

**args (model fills):**
- `path` (string, required) — destination path.
- `content` (string, required) — full file content as a single string.

**example:** create a small note

  <tool:file_write>{"path":"~/scratch/note.md","content":"# Note\n\nFirst line.\n"}</tool>
