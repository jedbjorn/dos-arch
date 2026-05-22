---
name: file_delete
description: Delete a file. Destructive. Refuses a directory.
kind: builtin
handler: file.delete
---
{
  "type": "object",
  "properties": {
    "path": {
      "type": "string",
      "description": "file to delete"
    }
  },
  "required": [
    "path"
  ]
}
