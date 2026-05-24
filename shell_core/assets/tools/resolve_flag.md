---
name: resolve_flag
description: Resolve, reopen, or set tracking on a flag by id. UNPROMPTED for resolve; the flag_id and a status are the model's job.
kind: builtin
handler: flag.resolve
---
<!-- @@ SPEC @@ -->
{
  "type": "object",
  "properties": {
    "flag_id": {
      "type": "integer",
      "description": "The flag's id (from the OPEN FLAGS pointer or a prior list)."
    },
    "status": {
      "type": "integer",
      "enum": [0, 1, 2],
      "description": "0 = Open, 1 = Resolved, 2 = Tracking."
    },
    "notes": {
      "type": "string",
      "description": "Optional resolution notes — appended to the flag's resolution_notes."
    }
  },
  "required": ["flag_id", "status"]
}

<!-- @@ PROMPT @@ -->
### resolve_flag — resolve, reopen, or set tracking on a flag

**use when:** closing out a flag (status=1), reopening one (status=0), or moving it to tracking (status=2). UNPROMPTED for resolve.

**args (model fills):**
- `flag_id` (integer, required) — the flag's id.
- `status` (integer, required) — `0` Open · `1` Resolved · `2` Tracking.
- `notes` (string, optional) — appended to the flag's resolution notes with the action stamp.

**example:** resolve a flag with a one-line note

  <tool:resolve_flag>{"flag_id":79,"status":1,"notes":"Shipped as PR #103. Per-tool prompt_block + multi-section asset format + reseed migrations."}</tool>
