---
name: api_delete
description: DELETE request to the dos-arch API. Optional JSON body.
kind: builtin
handler: api
---
<!-- @@ SPEC @@ -->
{
  "type": "object",
  "properties": {
    "path": { "type": "string" },
    "body": { "type": "object", "description": "Optional JSON body." }
  },
  "required": ["path"]
}

<!-- @@ PROMPT @@ -->
### api_delete — delete on the substrate API

**use when:** the substrate exposes a DELETE for the resource you want to remove. Most state on the substrate retires via PATCH (soft delete) rather than DELETE — verify the endpoint exists before reaching for this.

**args (model fills):**
- `path` (string, required) — API path starting with `/`.
- `body` (object, optional) — JSON body, only if the endpoint requires one.

**example:** delete a substrate resource

  <tool:api_delete>{"path":"/some-resource/42"}</tool>
