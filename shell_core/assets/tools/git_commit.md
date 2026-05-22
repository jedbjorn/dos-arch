---
name: git_commit
description: Commit staged changes with a message.
kind: builtin
handler: git.commit
---
{
  "type": "object",
  "properties": {
    "cwd": {
      "type": "string",
      "description": "repository working directory"
    },
    "message": {
      "type": "string",
      "description": "commit message"
    },
    "stage_all": {
      "type": "boolean",
      "description": "stage every change before committing"
    }
  },
  "required": [
    "cwd",
    "message"
  ]
}
