-- 036 — harden create_flag tool: positive-direction prose, required description,
-- per-field constraints (maxLength, minLength, pattern, enum, default, examples).
--
-- Fresh installs pick this up automatically via seed_from_assets reading
-- assets/tools/create_flag.md. This migration carries the same change to
-- substrates already bootstrapped with the prior (032) row — seed_from_assets
-- is INSERT-missing-only and will not refresh existing rows.
--
-- UPDATE (not INSERT OR IGNORE): the row exists everywhere by now; we want it
-- rewritten with the new description + spec.
--
-- Plain SQL: migrate.py owns the transaction and the schema_migrations row.

UPDATE tools
SET description = 'Open a new flag (blocker / work-of-record) for the calling shell. shell_id is set server-side from the bearer token. WHEN — the user asks to track a piece of work, open a blocker, or capture something that needs follow-up. SCOPE — opens new flags only; for listing open flags use surface_flags; for updating/resolving existing flags a separate tool is needed (surface that to FnB). CONVENTION — display_name is a short scoped headline; description follows ''[Area] {what & why} | Blocker for: {what unblocks}''. Both required — ask FnB for clarification if the brief is thin.',
    spec        = '{
  "type": "object",
  "required": ["display_name", "description"],
  "properties": {
    "display_name": {
      "type": "string",
      "maxLength": 80,
      "description": "Display name. Required. ~40-60 characters. Short scoped headline derived from the user''s request. Examples: ''Tools pivot — native function-calling only'', ''create_flag schema hardening'', ''Dispatcher reaper smoke-test failure''. Ask FnB for a title if the brief lacks one."
    },
    "description": {
      "type": "string",
      "minLength": 20,
      "description": "Description. Required. ~50-200 characters. Preferred shape: ''[Area] {what & why} | Blocker for: {what unblocks}''. [Area] is a scope tag like [Boot prompt], [Dispatcher], [Schema], [Flag tooling]. Derived from chat context — capture what the flag tracks, why it matters, and what unblocks on close. Ask FnB for clarification if context is thin.",
      "examples": [
        "[Boot prompt] Pivot TOOLS section to native function-calling only; drop parsed dialect path | Blocker for: parsed branch removal, models registry capability flags.",
        "[Flag tooling] Harden create_flag spec so 8B models produce well-formed flags from the schema alone | Blocker for: full purpose-built tool roster (decisions, identity entries, narrative append)."
      ]
    },
    "priority": {
      "type": "string",
      "enum": ["High", "Medium", "Low"],
      "default": "Medium",
      "description": "Priority. Not Required. Defaults to Medium. Use default or derive from context where priority is clear."
    },
    "start_date": {
      "type": "string",
      "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
      "description": "Start date. Not Required. ISO date (YYYY-MM-DD). Defaults to ''open now''. Set when the user named a date."
    },
    "parent_flag_id": {
      "type": "integer",
      "description": "Parent flag ID. Not Required. flag_id of an existing flag this one is a child of. Set when the user names a parent or the dependency is obvious."
    },
    "estimated_days": {
      "type": "number",
      "description": "Estimated days. Not Required. Rough effort estimate, fractional allowed (e.g. 0.5). Set when the user named one."
    }
  }
}
'
WHERE name = 'create_flag';
