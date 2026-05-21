-- 021 — drop shells.additional_prompt.
--
-- The per-shell operating protocol used to be a free-form blob in
-- `additional_prompt`, rendered into the boot prompt as one section. The
-- shell-prompt-renderer catalog (slices 1-6) replaced that: the universal
-- protocol is baked into `catalog_universal.md`, and the per-shell surfaces
-- are the `role` / `mandate` / `connections` columns. Neither render path
-- has read `additional_prompt` since the slice 4-5 cutovers — the column is
-- vestigial. Drop it.
--
-- `shell_system_prompt.md` (the template `additional_prompt` was rendered
-- from) is deleted in the same PR; `create_shell` and the `db_init` seeders
-- now write the `role` / `mandate` / `connections` columns directly.
--
-- Plain SQL: migrate.py owns the transaction and the schema_migrations row.

ALTER TABLE shells DROP COLUMN additional_prompt;
