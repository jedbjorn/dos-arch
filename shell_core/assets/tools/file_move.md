---
name: file_move
description: Move or rename a file.
kind: builtin
handler: file.move
---
{
  "type": "object",
  "properties": {
    "src": {
      "type": "string",
      "description": "source path"
    },
    "dst": {
      "type": "string",
      "description": "destination path"
    }
  },
  "required": [
    "src",
    "dst"
  ]
}
