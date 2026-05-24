---
name: api_patch
description: PATCH request to the dos-arch API. Body sent as JSON.
kind: builtin
handler: api
---
<!-- @@ SPEC @@ -->
{
  "type": "object",
  "properties": {
    "path": { "type": "string" },
    "body": { "type": "object" }
  },
  "required": ["path", "body"]
}

<!-- @@ PROMPT @@ -->
### api_patch — partial update on the substrate API

**use when:** mutating existing substrate state — updating a shell's `current_state` or `connections`, resolving a flag, retiring an identity entry — that has no named tool yet.

**args (model fills):**
- `path` (string, required) — API path starting with `/`.
- `body` (object, required) — JSON object of fields to update.

**example:** rewrite this shell's rolling current_state

  <tool:api_patch>{"path":"/shells/<self>","body":{"current_state":"<new tight status line>"}}</tool>
