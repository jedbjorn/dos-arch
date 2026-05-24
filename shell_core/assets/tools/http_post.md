---
name: http_post
description: HTTP POST with a body or a JSON payload.
kind: builtin
handler: net.http_post
---
<!-- @@ SPEC @@ -->
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

<!-- @@ PROMPT @@ -->
### http_post — outbound HTTP POST

**use when:** posting to an external HTTP service. **Not for the substrate API** — `api_post` and the named substrate tools handle that. Send either `json` (object) or `body` (raw string), not both.

**args (model fills):**
- `url` (string, required) — absolute URL.
- `json` (object, optional) — JSON request body (sets Content-Type automatically).
- `body` (string, optional) — raw request body. Use when the endpoint expects non-JSON.
- `headers` (object, optional) — request headers. Never embed secret values.

**example:** POST JSON to an external service

  <tool:http_post>{"url":"https://api.example.com/v1/events","json":{"type":"ping"}}</tool>
