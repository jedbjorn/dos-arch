-- 055 — condense bloated tool descriptions
--   create_flag, resolve_flag, create_decision, create_identity_entry
--
-- These four tool descriptions had the full skill procedure (WHEN/SCOPE/
-- CONVENTION) pasted into them — 573–807 chars each, duplicating the
-- canonical body in skills.content. The description ships in every boot
-- document and every provider tool schema (always-on); the skill content
-- is lazy-loaded. Condensed to ~200–240 chars: what the tool does + the one
-- non-obvious param convention + a WHEN cue for local (parsed) models. Depth
-- stays in skills.content. Mirrors the live edit; idempotent UPDATE.
--
-- Plain SQL: migrate.py owns the transaction and the schema_migrations row.

UPDATE tools SET description = 'Open a new flag — a blocker or work-of-record — for the calling shell; shell_id set server-side. Use when work needs tracking or follow-up. description format: "[Area] {what & why} | Blocker for: {what unblocks}".' WHERE name = 'create_flag';
UPDATE tools SET description = 'Close an open flag as work-of-record (PATCH /flags/{flag_id}/resolve); shell_id verified server-side. Fire when a blocker clears or the work concludes. resolution_notes = what shipped / learned / stays open, ~60–200 chars — "done" is too thin.' WHERE name = 'resolve_flag';
UPDATE tools SET description = 'Record a Major (M) decision — the canonical record; repo ADRs (DECISIONS.md) are mirrors, not substitutes. Fire on a major architectural or directional choice. decision = the choice in one line; rationale = the why.' WHERE name = 'create_decision';
UPDATE tools SET description = 'Record a seed (who you are) or L&S (how you work) entry; kind = "seed" | "lns". Append-only, never edited (Law 3). Mostly passive — fire when such a moment lands. body is prose only — seed past-tense, L&S imperative, no inline date.' WHERE name = 'create_identity_entry';
