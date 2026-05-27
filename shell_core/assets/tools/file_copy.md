---
name: file_copy
description: Copy a file to a new path. Refuses if the destination already exists.
kind: builtin
handler: file.copy
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
