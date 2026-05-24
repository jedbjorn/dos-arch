---
name: git_checkout
description: Switch to a branch, or create one.
kind: builtin
handler: git.checkout
---
{
  "type": "object",
  "properties": {
    "cwd": {
      "type": "string",
      "description": "repository working directory"
    },
    "branch": {
      "type": "string",
      "description": "branch name"
    },
    "create": {
      "type": "boolean",
      "description": "create the branch before switching"
    }
  },
  "required": [
    "cwd",
    "branch"
  ]
}
