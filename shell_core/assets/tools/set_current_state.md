---
name: set_current_state
description: Rewrite this shell's rolling current_state (now/next status line). Replaces the value — not a log. shell_id from Bearer.
kind: builtin
handler: current_state.set
---
<!-- @@ SPEC @@ -->
{
  "type": "object",
  "properties": {
    "current_state": {
      "type": "string",
      "description": "Tight now/next status line, ~280 chars soft cap."
    }
  },
  "required": ["current_state"]
}

<!-- @@ PROMPT @@ -->
### set_current_state — rewrite the rolling now/next

**use when:** focus shifts — `current_state` is a *rolling* status, **not a log**. Replace it whole; do not append. UNPROMPTED. Aim ~280 chars; the narrative carries the arc, this carries the present.

**args (model fills):**
- `current_state` (string, required) — the new tight status line.

**example:** update after shipping a PR

  <tool:set_current_state>{"current_state":"PR #103 opened: per-tool prompt_block + multi-section asset format. Awaiting Jed review. Next: CC-080 — named substrate tools on top."}</tool>
