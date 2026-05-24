---
name: url_fetch
description: Fetch a URL and return its plain-text body.
kind: builtin
handler: net.url_fetch
---
<!-- @@ SPEC @@ -->
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

<!-- @@ PROMPT @@ -->
### url_fetch — fetch a URL as plain text

**use when:** pulling readable text from a web page or doc URL. Simpler than `http_get` — no headers, no status, just text body.

**args (model fills):**
- `url` (string, required) — absolute URL.

**example:** read a doc

  <tool:url_fetch>{"url":"https://example.com/docs/intro.md"}</tool>
