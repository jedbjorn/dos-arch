-- 023 — drop shells.boot_document.
--
-- The boot document moved onto chat_sessions in migration 022. Since the
-- slice 2-4 cutover (PR #62) no code reads or writes shells.boot_document —
-- the deprecated column is dead. Drop it (substrate decision #123).
--
-- Plain SQL: migrate.py owns the transaction and the schema_migrations row.

ALTER TABLE shells DROP COLUMN boot_document;
