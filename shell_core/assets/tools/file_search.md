---
name: file_search
description: Search file contents for a pattern.
kind: builtin
handler: file.search
---
{
  "type": "object",
  "properties": {
    "pattern": {
      "type": "string",
      "description": "substring, or a regex when regex is true"
    },
    "path": {
      "type": "string",
      "description": "file or directory to search, defaults to the working dir"
    },
    "regex": {
      "type": "boolean",
      "description": "treat pattern as a regular expression"
    }
  },
  "required": [
    "pattern"
  ]
}
