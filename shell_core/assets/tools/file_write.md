---
name: file_write
description: Write a new file. Fails if the path already exists.
kind: builtin
handler: file.write
---
{
  "type": "object",
  "properties": {
    "path": {
      "type": "string",
      "description": "file path to create"
    },
    "content": {
      "type": "string",
      "description": "full file content"
    }
  },
  "required": [
    "path",
    "content"
  ]
}
