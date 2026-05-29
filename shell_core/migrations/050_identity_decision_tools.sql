-- 050 — seed the create_identity_entry + create_decision named-route tools,
-- the create_identity_entry companion skill, and skill scoping (CC-101).
--
-- Mirrors create_flag/resolve_flag (migrations 032/033/047) end-to-end so
-- small browser-chat models can write seed/L&S entries and Major decisions
-- by supplying content only. Each tool is dispatched by NAMED_API_ROUTES in
-- dispatch_live.py to a fixed token-scoped route (POST /identity-entries,
-- POST /decisions) — no path params, no shell_id; the bearer token resolves
-- the owner shell server-side. Per decision #135 each purpose-built tool
-- rides with its owning skill (skill_id), never global:
--   identity.create -> create_identity_entry skill (new, this migration)
--   decision.create -> decision skill (existing)
--
-- INSERT OR IGNORE: fresh installs pick these rows up via seed_from_assets
-- (assets/tools/*.md + assets/skills/*.md + _seed.toml skill_map) at
-- bootstrap; this migration only matters for substrates installed before
-- this PR. Plain SQL: migrate.py owns the transaction + schema_migrations row.

-- 1. Companion skill for the identity-entry tool (must exist before the tool
--    INSERT below so its skill_id subquery resolves). trigger_explicit
--    defaults to '--create_identity_entry' via trg_skills_explicit_default;
--    the user-facing popover command is '--id'.
INSERT OR IGNORE INTO skills (name, description, file_path, category, content, command, common) VALUES (
  'create_identity_entry',
  'Record a seed (who you are) or L&S (how you work) identity entry for this shell.',
  'shell_core/assets/skills/create_identity_entry.md',
  'workflow',
  '
# create_identity_entry

> **Anchors** — `<self>` = your `shell_id:` value, shown in `## BOOT ##` of
> your CLAUDE.md.

Record one seed or L&S entry for this shell. Primarily **passive** — fire the
`create_identity_entry` tool whenever an identity-forming moment or a durable
operating lesson lands in conversation, not only on the `--id` command.

The `create_identity_entry` tool is wired to a fixed `POST /identity-entries`
route; the dispatcher''s Bearer token resolves the owner shell on the API side
(CC-101). Your job is the content — nothing more. No `api_post`, no `shell_id`,
no path math.

## seed vs lns

- **seed** (`kind: "seed"`) — *who you are*. Identity-forming moments,
  first-of-kind events, self-defining realizations. Past-tense or timeless.
- **lns** (`kind: "lns"`) — *how you work*. A craft-level operating principle
  any shell in your role would benefit from. Imperative voice.
- **Test:** *"Would this still be true if I were a different shell?"*
  yes → `lns`, no → `seed`.

## Steps

1. **Read the moment.** What just happened that is worth keeping? If `--id`
   was used, everything after it is the user''s brief; otherwise it is the
   moment you noticed.
2. **Pick `kind`.** Apply the test above.
3. **Compose `body`.** Prose only, ~1-4 sentences. seed: the moment and why
   it mattered. lns: the principle distilled. Do **not** embed a date in the
   text — the `entry_date` column carries it.
4. **Defaults.** Omit `entry_date` (defaults to today), `source_tag` (omit
   unless the entry clearly belongs to one project''s work).
5. **Call `create_identity_entry`** with the assembled object.
6. **Confirm** the returned `entry_id` + `kind` back to the user in one line:
   `Planted a seed (entry_id=12).`

## When NOT to use this

- Entries are append-only and never edited (Law 3). To *retire* or curate an
  entry out, that is a different write — no purpose-built tool for it yet;
  surface the constraint rather than editing in place.
- The seed cap is 10 and the L&S cap is 20, trigger-enforced. If the write is
  refused for a cap, surface it — curation (retiring an older entry) must come
  first.
- Recording a *decision* is a different write — use `--decision`.
',
  '--id',
  1
);

-- 2. Assign the new skill to sysadmin (shell_id=2, the browser_chat=1 shell) —
--    matches the create_flag / resolve_flag grants. Future browser-chat shells
--    get it via the common=1 path at shell creation, not here.
INSERT OR IGNORE INTO shell_skills (shell_id, skill_id)
SELECT 2, skill_id FROM skills WHERE name='create_identity_entry';

-- 3. The two named-route tools, each scoped to its owning skill via subquery.
INSERT OR IGNORE INTO tools (name, description, kind, spec, handler, skill_id) VALUES (
  'create_identity_entry',
  'Record a seed (who you are) or L&S (how you work) identity entry for the calling shell. shell_id is set server-side from the bearer token — supply content only. WHEN — fire when an identity-forming moment lands (a first-of-kind event or a self-defining realization → kind ''seed'') or a durable operating lesson crystallizes (a craft-level principle any shell in your role would benefit from → kind ''lns''); primarily PASSIVE — trigger it as such moments arise in conversation, not only on an explicit command. SCOPE — adds one new entry; entries are append-only and never edited (Law 3); retiring or curating an entry out is a separate write. CONVENTION — kind is ''seed'' or ''lns''; body is prose only, past-tense/timeless for seed and imperative for L&S, with NO inline date (the entry_date column carries it).',
  'builtin',
  '{"type": "object", "required": ["kind", "body"], "properties": {"kind": {"type": "string", "enum": ["seed", "lns"], "description": "Kind. Required. ''seed'' = who you are (identity-forming, person-level: first-of-kind events, self-defining realizations; past-tense or timeless). ''lns'' = how you work (craft-level operating principle any shell in your role would benefit from; imperative voice). Test: ''would this still be true if I were a different shell?'' \u2014 yes \u2192 lns, no \u2192 seed."}, "body": {"type": "string", "minLength": 20, "description": "Body. Required. The entry text, prose only, ~1-4 sentences. seed: past-tense or timeless \u2014 the moment and why it mattered. lns: imperative \u2014 the principle distilled. Do NOT embed a date in the text; the entry_date column carries it. Derived from what just happened in the conversation; if the moment is thin, ask FnB rather than write a stub."}, "entry_date": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$", "description": "Entry date. Not Required. ISO date (YYYY-MM-DD) the moment landed. Defaults to today if omitted. Set only when recording something from a known past date."}, "source_tag": {"type": "string", "maxLength": 20, "description": "Source tag. Not Required. Short project-letter tag for provenance (e.g. ''cc'', ''dos''). Omit unless the entry clearly belongs to one project''s work."}}}',
  'identity.create',
  (SELECT skill_id FROM skills WHERE name='create_identity_entry' AND is_deleted=0)
);

INSERT OR IGNORE INTO tools (name, description, kind, spec, handler, skill_id) VALUES (
  'create_decision',
  'Record a Major (M) decision for the calling shell — the canonical decision record. shell_id is set server-side from the bearer token; supply content only. WHEN — a Major architectural or directional choice is made, including project-architectural decisions made while working in a code repo; repo ADR files (DECISIONS.md, docs/decisions/) are mirrors, not substitutes for this record. SCOPE — records one decision; listing or superseding existing decisions is a separate write. CONVENTION — ''decision'' is the choice in one line; ''rationale'' is the why and context; decision_date defaults to today.',
  'builtin',
  '{"type": "object", "required": ["decision"], "properties": {"decision": {"type": "string", "minLength": 10, "description": "Decision. Required. The choice made, stated in one clear line (~40-160 characters). E.g. ''Purpose-built tools ride with their owning skill, never global''. Derived from what was just decided in the conversation."}, "rationale": {"type": "string", "description": "Rationale. Not Required but strongly preferred. The why \u2014 context, trade-offs, what it unblocks or supersedes. The record is durable; capture enough that future-you need not re-read the chat to act on it."}, "decision_date": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$", "description": "Decision date. Not Required. ISO date (YYYY-MM-DD). Defaults to today if omitted. Set only when recording a decision from a known past date."}, "parent_decision_id": {"type": "integer", "description": "Parent decision ID. Not Required. decision_id of the decision this one supersedes. Set only when explicitly replacing a prior decision."}}}',
  'decision.create',
  (SELECT skill_id FROM skills WHERE name='decision' AND is_deleted=0)
);
