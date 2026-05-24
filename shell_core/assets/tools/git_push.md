---
name: git_push
description: Push commits to upstream.
kind: builtin
handler: git.push
---
{
  "type": "object",
  "properties": {
    "cwd": {
      "type": "string",
      "description": "repository working directory"
    },
    "force": {
      "type": "boolean",
      "description": "force-with-lease the push"
    }
  },
  "required": [
    "cwd"
  ]
}
