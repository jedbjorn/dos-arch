---
name: append_narrative
description: Append a line to this shell's active session narrative. shell_id + archive_id resolved server-side from the Bearer token.
kind: builtin
handler: narrative.append
---
<!-- @@ SPEC @@ -->
{
  "type": "object",
  "properties": {
    "narrative_entry": {
      "type": "string",
      "description": "One narrative line, format `[HH:MM] {1–2 lines}` per the memory protocol."
    }
  },
  "required": ["narrative_entry"]
}

<!-- @@ PROMPT @@ -->
### append_narrative — append to this session's narrative

**use when:** an inflection point lands in the session — a decision, an architecture change, a surprising find, before undertaking a major change, or an identity event. One line per write; format `[HH:MM] {1–2 lines}`. UNPROMPTED — no confirmation needed.

**args (model fills — shell + archive are resolved server-side):**
- `narrative_entry` (string, required) — the line to append. Include the `[HH:MM]` prefix.

**fails with 409** if this shell has no active archive (typical on API-model shells where `shell_memory_archives` is unpopulated). Surface that gap to the operator rather than working around it.

**example:** append a decision line

  <tool:append_narrative>{"narrative_entry":"[14:32] Decided to use server-side archive_id resolution rather than dispatcher-side lookup — keeps dispatcher dumb."}</tool>
