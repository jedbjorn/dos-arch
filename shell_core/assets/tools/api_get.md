---
name: api_get
description: GET request to the dos-arch API. Path may include a query string. Returns the response body as text.
kind: builtin
handler: api
---
<!-- @@ SPEC @@ -->
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

<!-- @@ PROMPT @@ -->
### api_get — read from the substrate API

**use when:** reading substrate state — flags, decisions, identity entries, archives — that has no named read tool. Reach for a named tool first when one exists; api_get is the general escape hatch. Endpoint catalog: `$DOS_API_URL/openapi.json`.

**args (model fills):**
- `path` (string, required) — API path starting with `/`, may include a query string.

**example:** list this shell's decisions

  <tool:api_get>{"path":"/shells/<self>/decisions"}</tool>
