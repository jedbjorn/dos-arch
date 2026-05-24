---
name: shared
description: Inspect this shell's shared host↔container handoff folder. Returns JSON {path, subdirs: {redlines: {count, latest}, review: {...}, repos: {...}, backups: {...}}}.
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
