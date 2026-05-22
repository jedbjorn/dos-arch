---
name: git_log
description: Show recent commits of a repository.
kind: builtin
handler: git.log
---
{
  "type": "object",
  "properties": {
    "cwd": {
      "type": "string",
      "description": "repository working directory"
    },
    "n": {
      "type": "integer",
      "description": "number of commits, defaults to 10"
    },
    "path": {
      "type": "string",
      "description": "limit the log to this path"
    }
  },
  "required": [
    "cwd"
  ]
}
