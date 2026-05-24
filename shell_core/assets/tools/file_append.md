---
name: file_append
description: Append content to the end of an existing file.
kind: builtin
handler: file.append
---
{
  "type": "object",
  "properties": {
    "path": {
      "type": "string",
      "description": "file to append to"
    },
    "content": {
      "type": "string",
      "description": "text to append"
    }
  },
  "required": [
    "path",
    "content"
  ]
}
