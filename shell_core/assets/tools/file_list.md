---
name: file_list
description: List the entries of a directory.
kind: builtin
handler: file.list
---
{
  "type": "object",
  "properties": {
    "path": {
      "type": "string",
      "description": "directory path"
    },
    "recursive": {
      "type": "boolean",
      "description": "recurse into subdirectories"
    }
  },
  "required": [
    "path"
  ]
}
