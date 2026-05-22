---
name: http_post
description: HTTP POST with a body or a JSON payload.
kind: builtin
handler: net.http_post
---
{
  "type": "object",
  "properties": {
    "url": {
      "type": "string",
      "description": "absolute URL"
    },
    "body": {
      "type": "string",
      "description": "optional raw request body"
    },
    "json": {
      "type": "object",
      "description": "optional JSON request body"
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
