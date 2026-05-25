-- 041 — new typed table dr_page + v_dr_catalogue extension.
--
-- The catalogue had no surface for SvelteKit pages. `dr_api` catalogues
-- every server route but the four pages under `ui/src/routes/` had no
-- equivalent — "where is the flags page" had to be answered by `find`.
-- This migration adds dr_page (one row per `+page.svelte`) and extends
-- v_dr_catalogue to UNION it.
--
-- dr_page mirrors the dr_lib shape: name + description_short + location,
-- UNIQUE on location (one row per file). No `kind` enum yet — all current
-- pages are SvelteKit; if a project clone introduces a second page system
-- (e.g. server-rendered Jinja), a `kind` column can be added then.
--
-- Like dr_db, dr_page is NOT added to v_shell_catalogue: pages are a
-- single global UI surface seen by every shell, so the per-shell projection
-- carries no signal. shell_dr_link's CHECK is left unchanged.

CREATE TABLE dr_page (
    page_id           INTEGER PRIMARY KEY,
    name              TEXT NOT NULL,
    description_short TEXT NOT NULL CHECK (LENGTH(description_short) <= 100),
    location          TEXT NOT NULL UNIQUE,
    purpose           TEXT,
    status            TEXT NOT NULL DEFAULT 'active'
                      CHECK (status IN ('active','deprecated','planned','retired')),
    last_verified     DATE,
    notes             TEXT
);

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
    SELECT 'dr_page', page_id, name, description_short FROM dr_page WHERE status = 'active'
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
