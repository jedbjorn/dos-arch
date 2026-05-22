-- 027 — git-workflow becomes opt-in.
--
-- git-workflow carries the 8 git tools (migration 026). As a common skill it
-- was auto-attached to every shell created with the 'common' bundle, so every
-- such shell rendered the git tools in its boot prompt. Git tooling should be
-- opt-in — a shell gets it only when git-workflow is explicitly assigned.
-- Flipping common to 0 takes it out of the default bundle; skill-scoped
-- rendering (migration 025) already gates the git tools on the assignment.
--
-- Forward-looking only: existing shells keep their shell_skills rows — on the
-- live DB only Sys-Admin holds git-workflow, and as a dev shell it should.
-- Removing it from a shell that should not have it is a targeted shell_skills
-- change, not this migration.
--
-- Plain SQL: migrate.py owns the transaction and the schema_migrations row.

UPDATE skills SET common = 0 WHERE name = 'git-workflow';
