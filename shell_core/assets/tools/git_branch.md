---
name: git_branch
description: List the local branches of a repository.
kind: builtin
handler: git.branch
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
