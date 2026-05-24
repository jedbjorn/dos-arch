---
name: git_diff
description: Show the diff of a repository, working tree or staged.
kind: builtin
handler: git.diff
---
{
  "type": "object",
  "properties": {
    "cwd": {
      "type": "string",
      "description": "repository working directory"
    },
    "staged": {
      "type": "boolean",
      "description": "show the staged diff instead of the working tree"
    },
    "path": {
      "type": "string",
      "description": "limit the diff to this path"
    }
  },
  "required": [
    "cwd"
  ]
}
