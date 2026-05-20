---
name: api_delete
description: DELETE request to the dos-arch API. Optional JSON body.
kind: builtin
handler: api
---
{
  "type": "object",
  "properties": {
    "path": { "type": "string" },
    "body": { "type": "object", "description": "Optional JSON body." }
  },
  "required": ["path"]
}
