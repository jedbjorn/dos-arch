-- 032 — seed the create_flag named-route tool.
--
-- A general tool (skill_id NULL — every shell gets it). Handler is
-- `flag.create`, dispatched by NAMED_API_ROUTES in dispatch_live.py to a
-- fixed POST /flags. The schema exposes only content fields; shell_id is
-- absent on purpose — the dispatcher's Bearer token resolves the owner
-- on the API side (migration 031). The model's job shrinks to "what is
-- this flag about"; nothing more.
--
-- INSERT OR IGNORE: fresh installs already picked up the row via
-- seed_from_assets reading assets/tools/create_flag.md at bootstrap; this
-- migration only matters for substrates installed before this PR.
--
-- Plain SQL: migrate.py owns the transaction and the schema_migrations row.

INSERT OR IGNORE INTO tools (name, description, kind, spec, handler) VALUES (
  'create_flag',
  'Open a new flag (work tracker / blocker). shell_id is filled from the calling shell''s Bearer token — the model only supplies content.',
  'builtin',
  '{"type": "object", "properties": {"display_name": {"type": "string", "description": "Short title, e.g. ''CC-077 cron-step hardening''."}, "description": {"type": "string", "description": "What the flag tracks. Free-form."}, "priority": {"type": "string", "enum": ["High", "Medium", "Low"], "description": "Defaults to ''Medium'' if omitted."}, "start_date": {"type": "string", "description": "ISO date (YYYY-MM-DD) when work begins. Omit if open now."}, "parent_flag_id": {"type": "integer", "description": "Existing flag this one is a child of."}, "estimated_days": {"type": "number", "description": "Rough effort estimate in days."}}, "required": ["display_name"]}',
  'flag.create'
);
