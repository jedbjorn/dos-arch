-- 047 — seed the resolve_flag named-route tool + companion skill.
--
-- Second purpose-built flag verb (after create_flag in migrations 032/033).
-- Handler is `flag.resolve`, dispatched by NAMED_API_ROUTES to a fixed
-- PATCH /flags/{flag_id}/resolve. The dispatcher substitutes {flag_id}
-- from the call input (templating added in this same PR); the bearer
-- token resolves the owner shell on the API side.
--
-- Schema exposes only flag_id + resolution_notes — no status field. This
-- tool resolves; reopen / set-tracking remain on the api_* surface for
-- now (surfaced in the skill's "When NOT to use this" section so weak
-- models name the gap instead of fabricating a call).
--
-- INSERT OR IGNORE: fresh installs pick the row up via seed_from_assets
-- reading assets/tools/resolve_flag.md + assets/skills/resolve_flag.md
-- at bootstrap; this migration matters for substrates installed before
-- this PR.
--
-- Plain SQL: migrate.py owns the transaction and the schema_migrations row.

INSERT OR IGNORE INTO tools (name, description, kind, spec, handler) VALUES (
  'resolve_flag',
  'Resolve an open flag (close it as work-of-record) for the calling shell. shell_id is verified server-side from the bearer token; the route is fixed (PATCH /flags/{flag_id}/resolve). WHEN — the user names a flag and signals it has closed, the blocker has cleared, or the work-of-record concludes. SCOPE — closes one flag at a time and appends resolution_notes; for opening flags use create_flag; for listing open flags use surface_flags; reopening or other status transitions remain on the api_* surface for now. CONVENTION — flag_id identifies the target (confirm via surface_flags if uncertain); resolution_notes is the *how* — what shipped, what was learned, what stays open. Aim for ~60-200 characters of substantive content; "done" or "resolved" alone is too thin to be useful.',
  'builtin',
  '{"type": "object", "required": ["flag_id", "resolution_notes"], "properties": {"flag_id": {"type": "integer", "minimum": 1, "description": "Flag ID. Required. Positive integer flag_id of the open flag to close. Confirm via surface_flags if uncertain; the user names the flag, you map it to the id."}, "resolution_notes": {"type": "string", "maxLength": 400, "description": "Resolution notes. Required. Aim for ~60-200 characters of substantive content — capture *how* the flag closed: what shipped, what was learned, what stays open. Avoid ''done'' or ''resolved'' alone; the row is the durable record. Derived from the work that just landed; if context is thin, ask FnB rather than write a stub."}}}',
  'flag.resolve'
);

INSERT OR IGNORE INTO skills (name, description, file_path, category, content, command, common) VALUES (
  'resolve_flag',
  'Close an open flag with substantive resolution notes.',
  'shell_core/assets/skills/resolve_flag.md',
  'workflow',
  '# resolve_flag

> **Anchors** — `<self>` = your `shell_id:` value, shown in `## BOOT ##` of
> your CLAUDE.md.

Close an open flag for this shell. Run on demand with `--resolve-flag`.

The `resolve_flag` tool is wired to a fixed `PATCH /flags/{flag_id}/resolve`
route; the dispatcher''s Bearer token resolves the owner shell on the API
side, and the dispatcher substitutes `{flag_id}` from the call input.
Your job is to identify the right flag and write substantive resolution
notes — nothing more. No `api_patch`, no path math.

## Steps

1. **Read the request.** Everything after `--resolve-flag` is the user''s
   brief on which flag closed and why.
2. **Identify the `flag_id`.** If the user named one by id, use it. If
   they named one by title, use `--flags` (surface_flags) to map title →
   id; confirm with FnB before mutating.
3. **Compose `resolution_notes`.** Capture: *what* shipped, *what* was
   learned, *what stays open* if anything. Aim for ~60-200 characters of
   substantive content. The row is the durable record — "done" or
   "resolved" alone is too thin.
4. **Call `resolve_flag`** with the assembled object.
5. **Confirm** the returned `flag_id` + `display_name` + new status back
   to the user in one line: `Closed CC-099 (flag_id=42).`

## When NOT to use this

- If the user is asking to *reopen* a closed flag — no purpose-built tool
  for that yet; surface the constraint and use `api_patch` if pressed.
- If they want to update fields without closing — no purpose-built tool;
  use `api_patch` and name the gap.
- If they want to delete — no tool exists; surface that.
- If they''re asking what''s open — use `--flags` (surface_flags).
',
  '--resolve-flag',
  1
);

-- Assign to sysadmin (shell_id=2) — the browser_chat=1 shell. Matches the
-- create_flag grant in migration 033. Future browser-chat shells get this
-- via the common=1 path at shell creation, not here.
INSERT OR IGNORE INTO shell_skills (shell_id, skill_id)
SELECT 2, skill_id FROM skills WHERE name='resolve_flag';
