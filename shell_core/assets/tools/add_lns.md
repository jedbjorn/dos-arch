---
name: add_lns
description: Add a Lessons & Stances entry (how-you-work). LAW 7 — curated, cap 20; bodies immutable.
kind: builtin
handler: lns.add
---
<!-- @@ SPEC @@ -->
{
  "type": "object",
  "properties": {
    "body": {
      "type": "string",
      "description": "Operating principle distilled from the job. Imperative voice. Re-learnable by any shell in your role."
    },
    "entry_date": {
      "type": "string",
      "description": "ISO date (YYYY-MM-DD). Defaults to today."
    },
    "source_tag": {
      "type": "string",
      "description": "Optional project-letter tag."
    }
  },
  "required": ["body"]
}

<!-- @@ PROMPT @@ -->
### add_lns — record a Lesson & Stance

**use when:** a lesson lands — an operating principle distilled from doing the job, in imperative voice, useful to any shell in your role. UNPROMPTED. Cap 20 — over-cap writes fail; retire one before adding another. Bodies are immutable post-write; revise via retire + re-add.

**args (model fills):**
- `body` (string, required) — the principle. Imperative voice.
- `entry_date` (string, optional) — ISO `YYYY-MM-DD`. Defaults to today.
- `source_tag` (string, optional) — project-letter tag.

**example:** record a stance

  <tool:add_lns>{"body":"When extending a generic asset seeder for a new column, push the splitting logic into the manifest contract — not into per-domain seed_X functions. Generic stays generic; the contract names the columns."}</tool>
