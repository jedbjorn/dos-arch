---
name: api_post
description: POST request to the dos-arch API. Body sent as JSON.
kind: builtin
handler: api
---
{
  "type": "object",
  "properties": {
    "path": { "type": "string" },
    "body": { "type": "object", "description": "JSON body." }
  },
  "required": ["path", "body"]
}
