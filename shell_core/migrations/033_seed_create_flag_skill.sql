-- 033 — seed the create_flag skill (user-clickable popover entry).
--
-- The create_flag *tool* shipped in migration 032 (PR #86) — model can
-- already call it. This migration adds the *skill* row so the chat
-- sidebar popover surfaces a clickable affordance: clicking populates
-- `--new-flag ` into the draft; the model then follows the skill body
-- (assets/skills/create_flag.md) to call the tool.
--
-- Fresh installs pick the skill up via seed_from_assets at bootstrap —
-- this migration only matters for substrates installed before this PR.
--
-- INSERT OR IGNORE on `skills` keeps re-runs idempotent. trigger_explicit
-- defaults to '--create_flag' via trg_skills_explicit_default after insert.
--
-- Plain SQL: migrate.py owns the transaction and the schema_migrations row.

INSERT OR IGNORE INTO skills (name, description, file_path, category, content, command, common) VALUES (
  'create_flag',
  'Open a new flag (work tracker / blocker) for this shell.',
  'shell_core/assets/skills/create_flag.md',
  'workflow',
  '# create_flag

> **Anchors** — `<self>` = your `shell_id:` value, shown in `## BOOT ##` of
> your CLAUDE.md.

Open a new flag for this shell. Run on demand with `--new-flag`.

The `create_flag` tool is wired to a fixed `POST /flags` route; the
dispatcher''s Bearer token resolves the owner shell on the API side
(migration 031). Your job is to gather the content fields — nothing more.
No `api_post`, no `shell_id`, no `flag_id` math.

## Steps

1. **Read the request.** Everything after `--new-flag` is the user''s brief.
   Free-form. Extract a short title + a longer description.
2. **Pick a `display_name`.** Short, distinctive, scoped (e.g.
   `CC-099 docs sweep` or `dispatcher reaper smoke-test`). The shell-prefix
   convention is optional — match what siblings on this shell already use.
3. **Compose `description`.** Capture: *what* the flag tracks, *why* it
   matters, and (if known) *what unblocks when it closes*. The flag is the
   work-of-record — be specific enough that future-you can act on it
   without re-reading this chat.
4. **Defaults.** Omit `priority` (defaults `Medium`), `start_date` (open
   now), `parent_flag_id` (none), `estimated_days` (unknown) unless the
   user named them. Don''t invent values.
5. **Call `create_flag`** with the assembled object.
6. **Confirm** the returned `flag_id` + `display_name` back to the user
   in one line: `Opened CC-099 (flag_id=42).`

## When NOT to use this

- If the user is asking to *resolve* or *update* an existing flag — that
  is a different write (no tool for it yet; surface that constraint
  rather than opening a duplicate).
- If they''re asking what''s open — use `--flags` (surface_flags).
',
  '--new-flag',
  1
);

-- Assign to sysadmin (shell_id=2) — the only browser_chat=1 shell today.
-- Future browser-chat shells get this via the common=1 grant path at
-- shell creation (Forge / create_shell), not here.
INSERT OR IGNORE INTO shell_skills (shell_id, skill_id)
SELECT 2, skill_id FROM skills WHERE name='create_flag';
