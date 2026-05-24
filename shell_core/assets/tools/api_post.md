---
name: api_post
description: POST request to the dos-arch API. Body sent as JSON.
kind: builtin
handler: api
---
<!-- @@ SPEC @@ -->
{
  "type": "object",
  "properties": {
    "path": { "type": "string" },
    "body": { "type": "object", "description": "JSON body." }
  },
  "required": ["path", "body"]
}

<!-- @@ PROMPT @@ -->
### api_post — create on the substrate API

**use when:** writing substrate state — opening a decision, posting an identity entry — that has no named write tool. Use the named tool when one exists (e.g. `create_flag`); api_post is the general fallback.

**args (model fills):**
- `path` (string, required) — API path starting with `/`.
- `body` (object, required) — JSON body. Shape per endpoint; see `$DOS_API_URL/openapi.json`.

**example:** record a decision for this shell

  <tool:api_post>{"path":"/shells/<self>/decisions","body":{"decision_date":"YYYY-MM-DD","priority":"M","decision":"<what>","rationale":"<why>"}}</tool>
