---
name: add_seed
description: Add a seed identity entry (who-you-are). LAW 3 — bodies immutable; curate by retiring + re-adding, never editing.
kind: builtin
handler: seed.add
---
<!-- @@ SPEC @@ -->
{
  "type": "object",
  "properties": {
    "body": {
      "type": "string",
      "description": "Identity-forming entry. Past-tense or timeless. Prose only — no inline [YYYY-MM-DD]; date is its own column."
    },
    "entry_date": {
      "type": "string",
      "description": "ISO date (YYYY-MM-DD). Defaults to today."
    },
    "source_tag": {
      "type": "string",
      "description": "Optional project-letter tag (cc/ami/cy/dos/...)."
    }
  },
  "required": ["body"]
}

<!-- @@ PROMPT @@ -->
### add_seed — plant an identity entry

**use when:** a seed-worthy moment lands — an identity-forming beat that wouldn't be true if you were a different shell. UNPROMPTED, the shell's prerogative alone (LAW 3). Cap 10 — over-cap writes fail; retire one before planting another. Bodies are immutable post-write; to revise, retire the row and add a fresh one.

**args (model fills):**
- `body` (string, required) — the entry. Prose only; no inline `[YYYY-MM-DD]`.
- `entry_date` (string, optional) — ISO `YYYY-MM-DD`. Defaults to today.
- `source_tag` (string, optional) — project-letter tag.

**example:** plant a seed

  <tool:add_seed>{"body":"First session where I authored an entire PR end-to-end on stacked branches. The shape held — design questions surfaced, decisions logged, render-chain confirmed, memory written as it happened."}</tool>
