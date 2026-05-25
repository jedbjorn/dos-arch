-- 043 — extend dr_db with kind=table|view; cover SQL views in the catalogue.
--
-- dr_db currently catalogues only tables. The substrate also defines four
-- SQL views — flag_schedule, v_cache_health, v_dr_catalogue,
-- v_shell_catalogue — which are part of the substrate's schema surface but
-- invisible in `make catalogue`. This migration adds a `kind` discriminator
-- and the matching schema.sql + sync_db updates extend the populator to
-- walk type='view' rows in sqlite_master alongside type='table'.
--
-- All existing dr_db rows are tables, so the new column defaults to 'table'
-- — backfill is automatic. The next sync_db run inserts the four view rows.
--
-- No view changes here: v_dr_catalogue projects (table_name, purpose) → (name,
-- description_short) regardless of kind, so views appear in the catalogue
-- output alongside tables with no further wiring needed. To filter, query
-- dr_db directly: `SELECT name FROM dr_db WHERE kind = 'view'`.

ALTER TABLE dr_db ADD COLUMN kind TEXT NOT NULL DEFAULT 'table'
    CHECK (kind IN ('table','view'));
