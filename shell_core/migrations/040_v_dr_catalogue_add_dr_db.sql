-- 040 — add dr_db to v_dr_catalogue.
--
-- PR CC-087 wires sync_db() — a new sync target populating dr_db with one
-- row per real substrate table (sqlite_master walk + curated purpose map).
-- Until now dr_db was empty and absent from the surfacing view, so
-- `make catalogue` had no answer for "what tables does the substrate have
-- and what are they for?". This migration extends v_dr_catalogue to UNION
-- in dr_db.
--
-- dr_db is intentionally NOT added to v_shell_catalogue: DB tables are
-- global to the substrate, not per-shell, so the shell_dr_link projection
-- would carry no meaningful information. shell_dr_link's CHECK constraint
-- remains unchanged.
--
-- dr_db has no `description_short` column — we project `purpose` into that
-- slot, matching the (ref_table, ref_id, name, description_short) shape
-- the other branches use. Rows with purpose=NULL still appear; the catalogue
-- output surfaces them as "(no purpose)" so undocumented tables are visible.

DROP VIEW IF EXISTS v_dr_catalogue;

CREATE VIEW v_dr_catalogue AS
    SELECT 'dr_repo' AS ref_table, repo_id AS ref_id, name, description_short FROM dr_repo WHERE status = 'active'
    UNION ALL
    SELECT 'dr_filepath', filepath_id, name, description_short FROM dr_filepath WHERE status = 'active'
    UNION ALL
    SELECT 'dr_router', router_id, name, description_short FROM dr_router WHERE status = 'active'
    UNION ALL
    SELECT 'dr_api', api_id, name, description_short FROM dr_api WHERE status = 'active'
    UNION ALL
    SELECT 'dr_lib', lib_id, name, description_short FROM dr_lib WHERE status = 'active'
    UNION ALL
    SELECT 'dr_dependencies', dep_id, name, description_short FROM dr_dependencies WHERE status = 'active'
    UNION ALL
    SELECT 'dr_services', service_id, name, description_short FROM dr_services WHERE status = 'active'
    UNION ALL
    SELECT 'dr_automations', automation_id, name, description_short FROM dr_automations WHERE status = 'active'
    UNION ALL
    SELECT 'dr_env', env_id, name, description_short FROM dr_env WHERE status = 'active'
    UNION ALL
    SELECT 'dr_db', db_id, table_name, purpose FROM dr_db WHERE status = 'active';
