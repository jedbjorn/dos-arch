---
name: http_get
description: HTTP GET. Returns status, headers, and body.
kind: builtin
handler: net.http_get
---
{
  "type": "object",
  "properties": {
    "url": {
      "type": "string",
      "description": "absolute URL"
    },
    "headers": {
      "type": "object",
      "description": "optional request headers"
    }
  },
  "required": [
    "url"
  ]
}
