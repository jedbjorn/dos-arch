---
name: file_apply_patch
description: Apply a batch of structured edits across one or more files atomically — all hunks succeed or none are written. Each hunk is a (path, old_str, new_str) triple with the same uniqueness rule as file_edit.
kind: builtin
handler: file.apply_patch
---
{
  "type": "object",
  "properties": {
    "hunks": {
      "type": "array",
      "description": "ordered list of edits to apply atomically",
      "items": {
        "type": "object",
        "properties": {
          "path": {
            "type": "string",
            "description": "file path to edit"
          },
          "old_str": {
            "type": "string",
            "description": "exact substring to replace; must match uniquely in the file"
          },
          "new_str": {
            "type": "string",
            "description": "replacement substring"
          }
        },
        "required": [
          "path",
          "old_str",
          "new_str"
        ]
      },
      "minItems": 1
    }
  },
  "required": [
    "hunks"
  ]
}
