-- 025 — tools become skill-scoped; shell_tools retired.
--
-- A tool is now either general or skill-bound:
--   general     — skill_id NULL. Every shell renders and can call it; the
--                 substrate api_* verbs (memory operations) are general.
--   skill-bound — skill_id set. Rendered in the boot prompt and callable
--                 only for shells granted the owning skill.
--
-- This makes the skill the unit of tool granting: attaching a skill brings
-- its tools. shell_tools — the per-shell tool grant — is therefore redundant
-- and dropped; the skill grant (shell_skills) plus the universal general
-- tools are the whole tool set. render_tools() and the dispatcher's
-- load_tools() resolve that effective set.
--
-- No backfill: the four existing api_* tools are general and keep skill_id
-- NULL (the ALTER's default). Dropping shell_tools loses the old per-shell
-- grant rows, but they only ever granted those four general tools, which
-- every shell now gets by the skill_id-NULL rule — so no shell loses a tool.
--
-- Plain SQL: migrate.py owns the transaction and the schema_migrations row.

ALTER TABLE tools ADD COLUMN skill_id INTEGER REFERENCES skills(skill_id);

DROP TABLE shell_tools;
