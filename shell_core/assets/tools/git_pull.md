---
name: git_pull
description: Pull from upstream. Fast-forward only by default.
kind: builtin
handler: git.pull
---
{
  "type": "object",
  "properties": {
    "cwd": {
      "type": "string",
      "description": "repository working directory"
    },
    "rebase": {
      "type": "boolean",
      "description": "rebase instead of fast-forward"
    }
  },
  "required": [
    "cwd"
  ]
}
