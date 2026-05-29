-- 052 — remove the git tool family + git-workflow skill.
--
-- Positioning decision: dos-arch is a shell-system substrate, not a coding
-- agent. There are enough capable coding agents; a shell that wants git
-- drives it through proc.exec / the operator's own tooling, not a bespoke
-- git.* family this project has to carry and harden. So the eight git_*
-- tools (handler git.*, seeded in migrations 026/027) and the git-workflow
-- skill (skill_id wiring, _legacy 004/005) are retired.
--
-- Removed alongside this migration: assets/tools/git_*.md, assets/skills/
-- git-workflow.md, the git.* entries + import in services/tools/__init__.py,
-- services/tools/git.py, and the `git` skill_map line in tools/_seed.toml —
-- so fresh installs never seed them. This migration is the bridge for
-- substrates installed before this PR.
--
-- Hard delete is correct here (permanent scope removal, not a temporary
-- hide): no trigger or foreign key references tools.tool_id, the dr_*
-- catalogue describes the tools *table* not its rows, and no shell currently
-- holds the git-workflow grant. Tools are deleted before the skill so the
-- skill_id they carried is unreferenced when the skill row goes.
--
-- Plain SQL: migrate.py owns the transaction and the schema_migrations row.

DELETE FROM tools WHERE handler LIKE 'git.%';

DELETE FROM shell_skills
 WHERE skill_id IN (SELECT skill_id FROM skills WHERE name = 'git-workflow');

DELETE FROM skills WHERE name = 'git-workflow';
