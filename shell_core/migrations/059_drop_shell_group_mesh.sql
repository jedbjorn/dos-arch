-- 059 — drop the shell-group mesh, replaced by user_projects (058).
--
-- docs/core-data-model.md abandons shell-level scoping: visibility is derived
-- (shell → user → user_projects → projects), not stored. The four mesh tables
-- are removed. All are empty in the live DB, and the sole code consumer —
-- shell_render.render_active_projects — is repointed to user_projects in the
-- same change, so this drop strands nothing.
--
-- Order: drop the dependents (project_groups, shell_group_members both FK
-- shell_groups; project_shells FKs projects+shells) before shell_groups. SQLite
-- doesn't enforce FKs at DROP, but dropping in dependency order keeps the
-- intent legible. Indexes drop with their tables.
--
-- Plain SQL: migrate.py owns the transaction and the schema_migrations row.

DROP TABLE IF EXISTS project_groups;
DROP TABLE IF EXISTS shell_group_members;
DROP TABLE IF EXISTS project_shells;
DROP TABLE IF EXISTS shell_groups;
