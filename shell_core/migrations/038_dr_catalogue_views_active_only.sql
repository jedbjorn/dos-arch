-- 038 — filter v_dr_catalogue and v_shell_catalogue to status='active'.
--
-- The typed dr_* registries preserve history: rows whose source declaration
-- is gone get transitioned to status='retired' rather than deleted (so
-- "what used to be here" is queryable). Both surfacing views, however,
-- UNION ALL across the typed tables without filtering on status, so
-- `surface_catalogue` shows active and retired side-by-side.
--
-- For a "where does X live right now" surface, that is the wrong default.
-- Retire history stays available by querying the dr_* tables directly.
--
-- This migration: DROP + recreate both views with `WHERE x.status = 'active'`
-- added to each branch. schema.sql is updated in lockstep so fresh
-- bootstraps pick up the same definition.

DROP VIEW IF EXISTS v_dr_catalogue;
DROP VIEW IF EXISTS v_shell_catalogue;

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
    SELECT 'dr_env', env_id, name, description_short FROM dr_env WHERE status = 'active';

CREATE VIEW v_shell_catalogue AS
    SELECT l.shell_id, 'dr_repo' AS ref_table, l.ref_id, x.name, x.description_short, l.role
        FROM shell_dr_link l JOIN dr_repo x ON l.ref_id = x.repo_id
        WHERE l.ref_table = 'dr_repo' AND x.status = 'active'
    UNION ALL
    SELECT l.shell_id, 'dr_filepath', l.ref_id, x.name, x.description_short, l.role
        FROM shell_dr_link l JOIN dr_filepath x ON l.ref_id = x.filepath_id
        WHERE l.ref_table = 'dr_filepath' AND x.status = 'active'
    UNION ALL
    SELECT l.shell_id, 'dr_router', l.ref_id, x.name, x.description_short, l.role
        FROM shell_dr_link l JOIN dr_router x ON l.ref_id = x.router_id
        WHERE l.ref_table = 'dr_router' AND x.status = 'active'
    UNION ALL
    SELECT l.shell_id, 'dr_api', l.ref_id, x.name, x.description_short, l.role
        FROM shell_dr_link l JOIN dr_api x ON l.ref_id = x.api_id
        WHERE l.ref_table = 'dr_api' AND x.status = 'active'
    UNION ALL
    SELECT l.shell_id, 'dr_lib', l.ref_id, x.name, x.description_short, l.role
        FROM shell_dr_link l JOIN dr_lib x ON l.ref_id = x.lib_id
        WHERE l.ref_table = 'dr_lib' AND x.status = 'active'
    UNION ALL
    SELECT l.shell_id, 'dr_dependencies', l.ref_id, x.name, x.description_short, l.role
        FROM shell_dr_link l JOIN dr_dependencies x ON l.ref_id = x.dep_id
        WHERE l.ref_table = 'dr_dependencies' AND x.status = 'active'
    UNION ALL
    SELECT l.shell_id, 'dr_services', l.ref_id, x.name, x.description_short, l.role
        FROM shell_dr_link l JOIN dr_services x ON l.ref_id = x.service_id
        WHERE l.ref_table = 'dr_services' AND x.status = 'active'
    UNION ALL
    SELECT l.shell_id, 'dr_automations', l.ref_id, x.name, x.description_short, l.role
        FROM shell_dr_link l JOIN dr_automations x ON l.ref_id = x.automation_id
        WHERE l.ref_table = 'dr_automations' AND x.status = 'active'
    UNION ALL
    SELECT l.shell_id, 'dr_env', l.ref_id, x.name, x.description_short, l.role
        FROM shell_dr_link l JOIN dr_env x ON l.ref_id = x.env_id
        WHERE l.ref_table = 'dr_env' AND x.status = 'active';
