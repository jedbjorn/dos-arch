---
name: api_patch
description: PATCH request to the dos-arch API. Body sent as JSON.
kind: builtin
handler: api
---
{
  "type": "object",
  "properties": {
    "path": { "type": "string" },
    "body": { "type": "object" }
  },
  "required": ["path", "body"]
}
