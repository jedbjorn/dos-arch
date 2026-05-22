---
name: file_find
description: Find files by name using glob semantics.
kind: builtin
handler: file.find
---
{
  "type": "object",
  "properties": {
    "name_pattern": {
      "type": "string",
      "description": "glob pattern, e.g. *.py"
    },
    "path": {
      "type": "string",
      "description": "directory to search under, defaults to the working dir"
    }
  },
  "required": [
    "name_pattern"
  ]
}
