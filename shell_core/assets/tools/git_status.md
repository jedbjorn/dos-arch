---
name: git_status
description: Show the working-tree status of a repository.
kind: builtin
handler: git.status
---
{
  "type": "object",
  "properties": {
    "cwd": {
      "type": "string",
      "description": "repository working directory"
    }
  },
  "required": [
    "cwd"
  ]
}
