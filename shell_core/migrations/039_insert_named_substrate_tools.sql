-- 039 — insert 8 named substrate tools (CC-080).
--
-- PR #103 (CC-079) added `tools.prompt_block`. This migration uses it:
-- INSERT OR IGNORE one row per named tool — content-only schema (spec),
-- the per-tool TOOLS-section block (prompt_block), and the dispatcher
-- handler key (NAMED_API_ROUTES in dispatch_live.py). Fresh installs
-- pick the rows up via seed_from_assets at bootstrap; this migration
-- only matters for substrates installed before this PR.
--
-- skill_id NULL on all rows — these are substrate operations every shell
-- can call, not skill-bound utilities.
--
-- Plain SQL: migrate.py owns the transaction and the schema_migrations row.

INSERT OR IGNORE INTO tools (name, description, kind, handler, spec, prompt_block) VALUES (
  'create_decision',
  'Record a major decision (canonical row in shell_decisions). shell_id is filled from the calling shell''s Bearer token — the model only supplies content.',
  'builtin',
  'decision.create',
  '{
  "type": "object",
  "properties": {
    "decision":           { "type": "string", "description": "What was decided. One tight sentence." },
    "rationale":          { "type": "string", "description": "Why — the context that makes the decision make sense later." },
    "priority":           { "type": "string", "enum": ["M"], "description": "Major decisions only. Defaults to ''M''." },
    "decision_date":      { "type": "string", "description": "ISO date (YYYY-MM-DD). Defaults to today." },
    "parent_decision_id": { "type": "integer", "description": "Existing decision this one supersedes." }
  },
  "required": ["decision", "rationale"]
}',
  '### create_decision — record a major decision

**use when:** a Major (M-level) decision has been made and needs to land in the canonical decision log. Includes project-architectural decisions made while working in a code repo — repo ADR files are mirrors, not substitutes. Append-only; supersede by linking via `parent_decision_id`, never edit prior rows.

**args (model fills — shell_id is set from the Bearer token):**
- `decision` (string, required) — what was decided. One tight sentence.
- `rationale` (string, required) — why; the context that makes it make sense later.
- `priority` (string, optional) — currently only `M` (Major). Defaults to `M`.
- `decision_date` (string, optional) — ISO `YYYY-MM-DD`. Defaults to today.
- `parent_decision_id` (integer, optional) — id of the decision this one supersedes.

**example:** record an architectural decision

  <tool:create_decision>{"decision":"Tool prompts move from catalog_universal into per-tool prompt_block","rationale":"Local 8B can''t form a real call from name+desc. Each tool now carries its own block — name, when-to-use, args, example."}</tool>'
);

INSERT OR IGNORE INTO tools (name, description, kind, handler, spec, prompt_block) VALUES (
  'append_narrative',
  'Append a line to this shell''s active session narrative. shell_id + archive_id resolved server-side from the Bearer token.',
  'builtin',
  'narrative.append',
  '{
  "type": "object",
  "properties": {
    "narrative_entry": {
      "type": "string",
      "description": "One narrative line, format `[HH:MM] {1–2 lines}` per the memory protocol."
    }
  },
  "required": ["narrative_entry"]
}',
  '### append_narrative — append to this session''s narrative

**use when:** an inflection point lands in the session — a decision, an architecture change, a surprising find, before undertaking a major change, or an identity event. One line per write; format `[HH:MM] {1–2 lines}`. UNPROMPTED — no confirmation needed.

**args (model fills — shell + archive are resolved server-side):**
- `narrative_entry` (string, required) — the line to append. Include the `[HH:MM]` prefix.

**fails with 409** if this shell has no active archive (typical on API-model shells where `shell_memory_archives` is unpopulated). Surface that gap to the operator rather than working around it.

**example:** append a decision line

  <tool:append_narrative>{"narrative_entry":"[14:32] Decided to use server-side archive_id resolution rather than dispatcher-side lookup — keeps dispatcher dumb."}</tool>'
);

INSERT OR IGNORE INTO tools (name, description, kind, handler, spec, prompt_block) VALUES (
  'set_current_state',
  'Rewrite this shell''s rolling current_state (now/next status line). Replaces the value — not a log. shell_id from Bearer.',
  'builtin',
  'current_state.set',
  '{
  "type": "object",
  "properties": {
    "current_state": {
      "type": "string",
      "description": "Tight now/next status line, ~280 chars soft cap."
    }
  },
  "required": ["current_state"]
}',
  '### set_current_state — rewrite the rolling now/next

**use when:** focus shifts — `current_state` is a *rolling* status, **not a log**. Replace it whole; do not append. UNPROMPTED. Aim ~280 chars; the narrative carries the arc, this carries the present.

**args (model fills):**
- `current_state` (string, required) — the new tight status line.

**example:** update after shipping a PR

  <tool:set_current_state>{"current_state":"PR #103 opened: per-tool prompt_block + multi-section asset format. Awaiting Jed review. Next: CC-080 — named substrate tools on top."}</tool>'
);

INSERT OR IGNORE INTO tools (name, description, kind, handler, spec, prompt_block) VALUES (
  'add_seed',
  'Add a seed identity entry (who-you-are). LAW 3 — bodies immutable; curate by retiring + re-adding, never editing.',
  'builtin',
  'seed.add',
  '{
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
}',
  '### add_seed — plant an identity entry

**use when:** a seed-worthy moment lands — an identity-forming beat that wouldn''t be true if you were a different shell. UNPROMPTED, the shell''s prerogative alone (LAW 3). Cap 10 — over-cap writes fail; retire one before planting another. Bodies are immutable post-write; to revise, retire the row and add a fresh one.

**args (model fills):**
- `body` (string, required) — the entry. Prose only; no inline `[YYYY-MM-DD]`.
- `entry_date` (string, optional) — ISO `YYYY-MM-DD`. Defaults to today.
- `source_tag` (string, optional) — project-letter tag.

**example:** plant a seed

  <tool:add_seed>{"body":"First session where I authored an entire PR end-to-end on stacked branches. The shape held — design questions surfaced, decisions logged, render-chain confirmed, memory written as it happened."}</tool>'
);

INSERT OR IGNORE INTO tools (name, description, kind, handler, spec, prompt_block) VALUES (
  'add_lns',
  'Add a Lessons & Stances entry (how-you-work). LAW 7 — curated, cap 20; bodies immutable.',
  'builtin',
  'lns.add',
  '{
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
}',
  '### add_lns — record a Lesson & Stance

**use when:** a lesson lands — an operating principle distilled from doing the job, in imperative voice, useful to any shell in your role. UNPROMPTED. Cap 20 — over-cap writes fail; retire one before adding another. Bodies are immutable post-write; revise via retire + re-add.

**args (model fills):**
- `body` (string, required) — the principle. Imperative voice.
- `entry_date` (string, optional) — ISO `YYYY-MM-DD`. Defaults to today.
- `source_tag` (string, optional) — project-letter tag.

**example:** record a stance

  <tool:add_lns>{"body":"When extending a generic asset seeder for a new column, push the splitting logic into the manifest contract — not into per-domain seed_X functions. Generic stays generic; the contract names the columns."}</tool>'
);

INSERT OR IGNORE INTO tools (name, description, kind, handler, spec, prompt_block) VALUES (
  'resolve_flag',
  'Resolve, reopen, or set tracking on a flag by id. UNPROMPTED for resolve; the flag_id and a status are the model''s job.',
  'builtin',
  'flag.resolve',
  '{
  "type": "object",
  "properties": {
    "flag_id": {
      "type": "integer",
      "description": "The flag''s id (from the OPEN FLAGS pointer or a prior list)."
    },
    "status": {
      "type": "integer",
      "enum": [0, 1, 2],
      "description": "0 = Open, 1 = Resolved, 2 = Tracking."
    },
    "notes": {
      "type": "string",
      "description": "Optional resolution notes — appended to the flag''s resolution_notes."
    }
  },
  "required": ["flag_id", "status"]
}',
  '### resolve_flag — resolve, reopen, or set tracking on a flag

**use when:** closing out a flag (status=1), reopening one (status=0), or moving it to tracking (status=2). UNPROMPTED for resolve.

**args (model fills):**
- `flag_id` (integer, required) — the flag''s id.
- `status` (integer, required) — `0` Open · `1` Resolved · `2` Tracking.
- `notes` (string, optional) — appended to the flag''s resolution notes with the action stamp.

**example:** resolve a flag with a one-line note

  <tool:resolve_flag>{"flag_id":79,"status":1,"notes":"Shipped as PR #103. Per-tool prompt_block + multi-section asset format + reseed migrations."}</tool>'
);

INSERT OR IGNORE INTO tools (name, description, kind, handler, spec, prompt_block) VALUES (
  'list_flags',
  'List this shell''s flags. shell_id is filled from the Bearer token; the model only narrows by optional filters.',
  'builtin',
  'flag.list',
  '{
  "type": "object",
  "properties": {},
  "required": []
}',
  '### list_flags — list this shell''s flags

**use when:** surfacing this shell''s flags — open, resolved, or tracking — for triage. The OPEN FLAGS prompt pointer carries only the count; this tool reads the rows.

**args (model fills — shell_id is implicit from the Bearer token):**
- *(none required — defaults to all flags for this shell)*

**example:** list this shell''s flags

  <tool:list_flags>{}</tool>'
);

INSERT OR IGNORE INTO tools (name, description, kind, handler, spec, prompt_block) VALUES (
  'list_decisions',
  'List this shell''s decisions, with optional filters. shell_id from Bearer.',
  'builtin',
  'decision.list',
  '{
  "type": "object",
  "properties": {
    "q": {
      "type": "string",
      "description": "Substring match against decision text or rationale."
    },
    "priority": {
      "type": "string",
      "description": "Filter by priority. Currently only ''M''."
    },
    "date_from": {
      "type": "string",
      "description": "ISO date (YYYY-MM-DD). Decisions on or after."
    },
    "date_to": {
      "type": "string",
      "description": "ISO date (YYYY-MM-DD). Decisions on or before."
    }
  },
  "required": []
}',
  '### list_decisions — list this shell''s decisions

**use when:** reviewing prior decisions — searching the rationale log, scoping by date, or scanning recent context before a new write. Decisions are append-only; this is the read side.

**args (model fills — shell_id is implicit from the Bearer token):**
- `q` (string, optional) — substring match against decision text or rationale.
- `priority` (string, optional) — filter by priority. Currently only `M`.
- `date_from` (string, optional) — ISO `YYYY-MM-DD`; inclusive lower bound.
- `date_to` (string, optional) — ISO `YYYY-MM-DD`; inclusive upper bound.

**example:** search recent decisions for a keyword

  <tool:list_decisions>{"q":"prompt_block","date_from":"2026-05-01"}</tool>'
);
