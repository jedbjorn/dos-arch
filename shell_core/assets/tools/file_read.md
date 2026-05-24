---
name: file_read
description: Read a file from the working directory.
kind: builtin
handler: file.read
---
{
  "type": "object",
  "properties": {
    "path": {
      "type": "string",
      "description": "file path, ~ is expanded"
    },
    "lines": {
      "type": "array",
      "items": {
        "type": "integer"
      },
      "description": "optional [start, end] line numbers, 1-based inclusive"
    }
  },
  "required": [
    "path"
  ]
}
