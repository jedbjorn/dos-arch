---
name: http_get
description: HTTP GET. Returns status, headers, and body.
kind: builtin
handler: net.http_get
---
<!-- @@ SPEC @@ -->
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

<!-- @@ PROMPT @@ -->
### http_get — outbound HTTP GET

**use when:** fetching from an external HTTP service. **Not for the substrate API** — that is what `api_get` and the named substrate tools are for. Returns status, headers, body.

**args (model fills):**
- `url` (string, required) — absolute URL.
- `headers` (object, optional) — request headers. Never embed secret values here — reference variable names only if the dispatcher supports interpolation.

**example:** GET an external JSON endpoint

  <tool:http_get>{"url":"https://api.example.com/v1/status","headers":{"Accept":"application/json"}}</tool>
