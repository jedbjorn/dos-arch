---
name: api_get
description: GET request to the dos-arch API. Path may include a query string. Returns the response body as text.
kind: builtin
handler: api
---
{
  "type": "object",
  "properties": {
    "path": {
      "type": "string",
      "description": "API path including query, must start with /. e.g. \"/shells/2/decisions\""
    }
  },
  "required": ["path"]
}
