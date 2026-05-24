---
name: url_fetch
description: Fetch a URL and return its plain-text body.
kind: builtin
handler: net.url_fetch
---
{
  "type": "object",
  "properties": {
    "url": {
      "type": "string",
      "description": "absolute URL"
    }
  },
  "required": [
    "url"
  ]
}
