---
name: file_mkdir
description: Create a directory. Parents are created as needed; succeeds silently if the directory already exists.
kind: builtin
handler: file.mkdir
---
{
  "type": "object",
  "properties": {
    "path": {
      "type": "string",
      "description": "directory path to create"
    }
  },
  "required": [
    "path"
  ]
}
