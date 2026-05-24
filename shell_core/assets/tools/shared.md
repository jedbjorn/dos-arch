---
name: shared
description: Inspect this shell's shared host↔container handoff folder. Returns the absolute path plus a one-level listing (count + most-recent entry per subdir) of redlines/, review/, repos/, backups/.
kind: builtin
handler: shared.inspect
---
{
  "type": "object",
  "properties": {
    "shell_id": {
      "type": "integer",
      "description": "Your shell_id, from ## BOOT ## in your CLAUDE.md."
    },
    "shortname": {
      "type": "string",
      "description": "Your shortname, from ## IDENTITY ## in your CLAUDE.md."
    }
  },
  "required": ["shell_id", "shortname"]
}
