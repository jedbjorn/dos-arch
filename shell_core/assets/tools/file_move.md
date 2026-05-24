---
name: file_move
description: Move or rename a file.
kind: builtin
handler: file.move
---
<!-- @@ SPEC @@ -->
{
  "type": "object",
  "properties": {
    "src": {
      "type": "string",
      "description": "source path"
    },
    "dst": {
      "type": "string",
      "description": "destination path"
    }
  },
  "required": [
    "src",
    "dst"
  ]
}

<!-- @@ PROMPT @@ -->
### file_move — move or rename a file

**use when:** relocating or renaming a single file. Both paths are on the host filesystem.

**args (model fills):**
- `src` (string, required) — source path.
- `dst` (string, required) — destination path.

**example:** rename a file

  <tool:file_move>{"src":"~/scratch/old_name.md","dst":"~/scratch/new_name.md"}</tool>
