-- shell_infra — SQLite schema (substrate-only, single-user, no auth)
-- Phase 4 redesign. Stripped of CRM concepts (accounts/contacts/staff/team/
-- meetings/opportunities/email/aimail/notifications/mentions/follows) and of
-- the auth surface (sessions/password_hash/api_key/etc).

-- ── Identity ──────────────────────────────────────────────────────────────────

CREATE TABLE users (
    user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE,
    email         TEXT,
    initials      TEXT,
    password_hash TEXT,
    password_salt TEXT,
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    theme_bg      TEXT    DEFAULT '#0f1117',
    theme_accent  TEXT    DEFAULT '#0072FF',
    chat_history_window INTEGER
);

-- ── Shells ────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS "shells" (
    shell_id              INTEGER PRIMARY KEY,
    display_name          TEXT    NOT NULL,
    shortname             TEXT,
    partner               TEXT,
    role                  TEXT,
    mandate               TEXT,
    boot_document         TEXT,
    current_state         TEXT,
    connections           TEXT,
    api_endpoints         TEXT,
    lineage_seed          TEXT,
    browser_chat          INTEGER NOT NULL DEFAULT 0,
    ignore_messages       INTEGER NOT NULL DEFAULT 0,
    ignore_messages_since TIMESTAMP,
    has_identity          INTEGER NOT NULL DEFAULT 0,
    active_archive_id     INTEGER,
    user_id               INTEGER REFERENCES users(user_id),
    is_shared             INTEGER NOT NULL DEFAULT 0,
    is_admin              INTEGER NOT NULL DEFAULT 0,
    api_auth              INTEGER NOT NULL DEFAULT 0,
    api_key_hash          TEXT
);
-- api_auth: 0 = CLI shell — interactive Claude Code, browser-auth on first
--   launch (subscription billing), no Anthropic env, bypasses the broker's
--   /anthropic route. 1 = API shell — the launcher points it at the broker's
--   /anthropic route (ANTHROPIC_BASE_URL), which injects the real key. Any
--   shell exposing a web-app interface must be api_auth=1 (Anthropic ToS).

CREATE UNIQUE INDEX IF NOT EXISTS idx_shells_api_key_hash ON shells(api_key_hash);

CREATE TABLE IF NOT EXISTS "shell_memory_archives" (
    archive_id          INTEGER PRIMARY KEY,
    shell_id            INTEGER NOT NULL REFERENCES shells(shell_id),
    session_id          TEXT,
    date                DATE    NOT NULL,
    full_narrative      TEXT
);

CREATE TABLE shell_messages (
    message_id          INTEGER PRIMARY KEY,
    sender_id           INTEGER NOT NULL REFERENCES shells(shell_id),
    recipient_id        INTEGER NOT NULL REFERENCES shells(shell_id),
    subject             TEXT,
    body                TEXT    NOT NULL,
    sent_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    read                INTEGER NOT NULL DEFAULT 0,
    reply_to_message_id INTEGER REFERENCES shell_messages(message_id),
    user_issue          INTEGER NOT NULL DEFAULT 0,
    resolved            INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE shell_prompt_automations (
    prompt_auto_id  INTEGER PRIMARY KEY,
    display_name    TEXT,
    text            TEXT    NOT NULL,
    date            TIMESTAMP,
    successful      INTEGER NOT NULL DEFAULT 0,
    needs_attention INTEGER NOT NULL DEFAULT 0,
    shell_id        INTEGER NOT NULL REFERENCES shells(shell_id),
    is_recurring    INTEGER NOT NULL DEFAULT 0,
    cycles_expected INTEGER NOT NULL DEFAULT 0,
    cycles_complete INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE shell_logs (
    shell_log_id    INTEGER PRIMARY KEY,
    prompt          TEXT,
    line_lengths    TEXT,
    result          TEXT,
    relation_log    TEXT,
    validation      INTEGER NOT NULL DEFAULT 0,
    shell_id        INTEGER NOT NULL REFERENCES shells(shell_id),
    prompt_auto_id  INTEGER REFERENCES shell_prompt_automations(prompt_auto_id)
);

-- ── Skills ────────────────────────────────────────────────────────────────────

CREATE TABLE skills (
    skill_id    INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL,
    description TEXT,
    file_path   TEXT,
    category    TEXT,
    content     TEXT,
    command     TEXT,
    common      INTEGER NOT NULL DEFAULT 1,
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    trigger_explicit TEXT,                   -- the --name token (spec §07)
    trigger_keywords TEXT,                   -- comma-separated keyword list
    trigger_use_when TEXT                    -- one-sentence disambiguator
);

-- Default trigger_explicit to '--' || name on every insert that leaves it
-- NULL. Overridable: set trigger_explicit explicitly to keep a legacy /
-- short token. (Migration 020.)
CREATE TRIGGER trg_skills_explicit_default
AFTER INSERT ON skills
WHEN NEW.trigger_explicit IS NULL
BEGIN
  UPDATE skills SET trigger_explicit = '--' || NEW.name
  WHERE skill_id = NEW.skill_id;
END;

CREATE TABLE shell_skills (
    shell_skill_id  INTEGER PRIMARY KEY,
    shell_id        INTEGER NOT NULL REFERENCES shells(shell_id),
    skill_id        INTEGER NOT NULL REFERENCES skills(skill_id),
    UNIQUE(shell_id, skill_id)
);

-- ── Tools (provider-agnostic tooling-as-data) ─────────────────────────────────
-- The tool registry + per-shell grants, mirroring skills / shell_skills. A
-- shell's tool set is the shell_tools join; the dispatcher loads tool
-- definitions from here, not a hard-coded list (agnostic-runtime §4.2).

CREATE TABLE tools (
    tool_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    description TEXT,
    kind        TEXT    NOT NULL DEFAULT 'builtin'
                CHECK (kind IN ('builtin','script','mcp')),
    spec        TEXT,                       -- JSON parameter schema
    handler     TEXT,                       -- executor key (e.g. 'api')
    status      TEXT    NOT NULL DEFAULT 'active'
                CHECK (status IN ('active','inactive')),
    parsed_example TEXT                      -- parsed-dialect invocation example (spec §05)
);

CREATE TABLE shell_tools (
    shell_tool_id INTEGER PRIMARY KEY,
    shell_id      INTEGER NOT NULL REFERENCES shells(shell_id),
    tool_id       INTEGER NOT NULL REFERENCES tools(tool_id),
    UNIQUE (shell_id, tool_id)
);

-- ── Models (the agnostic-runtime registry) ────────────────────────────────────
-- Every model the system *can* use — provider, tool dialect, cost, limits.
-- Distinct from `installed_models` (the per-host Ollama install inventory).
-- The browser model-switch dropdown is populated from status='active' rows;
-- chat_sessions.model_id points one conversation at one row (agnostic-runtime
-- §4.1).

CREATE TABLE models (
    model_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT    NOT NULL UNIQUE,   -- claude-sonnet-4-6, gpt-5, ...
    display_name     TEXT,                      -- dropdown label
    provider         TEXT    NOT NULL
                     CHECK (provider IN ('anthropic','openai','google','local')),
    endpoint         TEXT,                      -- API base / local server URL
    auth_ref         TEXT,                      -- env-var NAME, never the secret
    tool_dialect     TEXT    NOT NULL DEFAULT 'anthropic'
                     CHECK (tool_dialect IN ('anthropic','openai','parsed')),
    context_window   INTEGER,
    max_output       INTEGER,
    capability_tags  TEXT,                      -- 'reasoning,code,vision'
    locality         TEXT    NOT NULL DEFAULT 'remote'
                     CHECK (locality IN ('remote','local')),
    vram_estimate_gb INTEGER,                   -- local models only
    version          TEXT,
    source_url       TEXT,
    cost_input       REAL,                      -- per-1M tokens; null for local
    cost_output      REAL,
    cost_cache_read  REAL,
    cost_cache_write REAL,
    status           TEXT    NOT NULL DEFAULT 'active'
                     CHECK (status IN ('active','inactive')),
    last_verified    TEXT
);

CREATE INDEX idx_models_status ON models (status);

-- ── Chat ──────────────────────────────────────────────────────────────────────

CREATE TABLE chat_sessions (
    chat_session_id    TEXT    PRIMARY KEY,
    shell_id           INTEGER NOT NULL REFERENCES shells(shell_id),
    user_id            INTEGER NOT NULL REFERENCES users(user_id),
    model_id           INTEGER REFERENCES models(model_id),
    started_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_active        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_active          INTEGER NOT NULL DEFAULT 1,
    total_tokens       INTEGER NOT NULL DEFAULT 0,
    token_warning_sent INTEGER NOT NULL DEFAULT 0,
    turn_in_flight_at         TIMESTAMP,
    turn_in_flight_message_id INTEGER REFERENCES chat_messages(message_id)
);

CREATE TABLE chat_messages (
    message_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    shell_id        INTEGER NOT NULL REFERENCES shells(shell_id),
    direction       TEXT    NOT NULL CHECK(direction IN ('inbound','outbound')),
    user_id         INTEGER REFERENCES users(user_id),
    body            TEXT    NOT NULL,
    sent_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    read_by_shell   INTEGER NOT NULL DEFAULT 0,
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    chat_session_id TEXT REFERENCES chat_sessions(chat_session_id),
    tokens          INTEGER
);

-- ── Flags (substrate task tracking) ───────────────────────────────────────────

CREATE TABLE IF NOT EXISTS "flags" (
    flag_id          INTEGER PRIMARY KEY,
    display_name     TEXT,
    priority         TEXT    NOT NULL CHECK(priority IN ('High','Medium','Low')),
    description      TEXT,
    created_date     DATE    NOT NULL,
    resolved_date    DATE,
    resolved         INTEGER NOT NULL DEFAULT 0,
    shell_id         INTEGER REFERENCES shells(shell_id),
    start_date       DATE,
    resolution_notes TEXT,
    is_deleted       INTEGER NOT NULL DEFAULT 0,
    parent_flag_id   INTEGER REFERENCES flags(flag_id),
    estimated_days   REAL
);

-- ── Shell identity entries (seed + L&S, table-backed with cap enforcement) ──

CREATE TABLE shell_identity_entries (
    entry_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    shell_id    INTEGER NOT NULL REFERENCES shells(shell_id),
    kind        TEXT    NOT NULL CHECK (kind IN ('seed', 'lns')),
    entry_date  TEXT,
    source_tag  TEXT,
    body        TEXT    NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    retired_at  TEXT,
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    priority    TEXT    CHECK (priority IN ('H','M','L')) DEFAULT 'M',
    pin         INTEGER NOT NULL DEFAULT 0
);

CREATE TRIGGER trg_sie_cap_seed
BEFORE INSERT ON shell_identity_entries
WHEN NEW.kind = 'seed' AND (
  SELECT COUNT(*) FROM shell_identity_entries
  WHERE shell_id = NEW.shell_id AND kind='seed'
    AND is_deleted=0 AND retired_at IS NULL
) >= 10
BEGIN
  SELECT RAISE(ABORT, 'seed cap (10) reached for this shell — retire an entry first');
END;

CREATE TRIGGER trg_sie_cap_lns
BEFORE INSERT ON shell_identity_entries
WHEN NEW.kind = 'lns' AND (
  SELECT COUNT(*) FROM shell_identity_entries
  WHERE shell_id = NEW.shell_id AND kind='lns'
    AND is_deleted=0 AND retired_at IS NULL
) >= 20
BEGIN
  SELECT RAISE(ABORT, 'L&S cap (20) reached for this shell — retire an entry first');
END;

-- Per-entry body length and current_state length are soft caps as of
-- migration 020 — a rendered ~target, no ABORT trigger. The count caps
-- above (trg_sie_cap_seed/lns) stay: curation, not tokens.

-- ── Projects (per-shell project memory + standing procedures) ────────────────

CREATE TABLE IF NOT EXISTS projects (
    project_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    shortname    TEXT NOT NULL UNIQUE,
    title        TEXT NOT NULL,
    purpose      TEXT,
    standing     TEXT,
    status       TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','inactive','paused')),
    is_deleted   INTEGER NOT NULL DEFAULT 0,
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS project_shells (
    project_shell_id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id       INTEGER NOT NULL REFERENCES projects(project_id),
    shell_id         INTEGER NOT NULL REFERENCES shells(shell_id),
    role             TEXT,
    added_date       DATE NOT NULL DEFAULT (date('now')),
    is_deleted       INTEGER NOT NULL DEFAULT 0,
    UNIQUE (project_id, shell_id)
);

-- ── Shell groups (lightweight permission boundary) ───────────────────────────
-- A shell sees only the projects in the groups it belongs to. Membership is
-- shell-level, not user-level: one user may own several shells with different
-- group membership (e.g. a specialized shell scoped to a single project).
-- An is_admin group's members bypass scoping and see every project.

CREATE TABLE IF NOT EXISTS shell_groups (
    group_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    slug        TEXT    NOT NULL UNIQUE,
    name        TEXT    NOT NULL,
    description TEXT,
    is_admin    INTEGER NOT NULL DEFAULT 0,
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS shell_group_members (
    membership_id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id      INTEGER NOT NULL REFERENCES shell_groups(group_id),
    shell_id      INTEGER NOT NULL REFERENCES shells(shell_id),
    added_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted    INTEGER NOT NULL DEFAULT 0,
    UNIQUE (group_id, shell_id)
);

CREATE TABLE IF NOT EXISTS project_groups (
    project_group_id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id   INTEGER NOT NULL REFERENCES shell_groups(group_id),
    project_id INTEGER NOT NULL REFERENCES projects(project_id),
    added_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    UNIQUE (group_id, project_id)
);

CREATE INDEX IF NOT EXISTS idx_shell_group_members_shell
    ON shell_group_members(shell_id);
CREATE INDEX IF NOT EXISTS idx_project_groups_group
    ON project_groups(group_id);

-- ── Shell decisions (per-shell decision log) ─────────────────────────────────

CREATE TABLE IF NOT EXISTS "shell_decisions" (
    decision_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    shell_id           INTEGER NOT NULL REFERENCES shells(shell_id),
    decision_date      DATE    NOT NULL,
    priority           TEXT    NOT NULL DEFAULT 'M' CHECK(priority IN ('M','m')),
    decision           TEXT    NOT NULL,
    rationale          TEXT,
    parent_decision_id INTEGER REFERENCES shell_decisions(decision_id),
    is_deleted         INTEGER NOT NULL DEFAULT 0,
    created_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ── Plans ─────────────────────────────────────────────────────────────────────

CREATE TABLE plans (
    plan_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    shell_id    INTEGER NOT NULL REFERENCES shells(shell_id),
    project     TEXT,
    title       TEXT NOT NULL,
    objective   TEXT NOT NULL,
    content     TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'draft'
                CHECK(status IN ('draft','active','complete','abandoned')),
    step_count  INTEGER,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── Audit log ─────────────────────────────────────────────────────────────────

CREATE TABLE app_ui_logs (
    log_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER REFERENCES users(user_id),
    timestamp   TEXT NOT NULL DEFAULT (datetime('now')),
    method      TEXT NOT NULL,
    path        TEXT NOT NULL,
    status_code INTEGER,
    duration_ms INTEGER,
    ip          TEXT,
    shell_id    INTEGER REFERENCES shells(shell_id)
);

-- ── Design references ─────────────────────────────────────────────────────────
-- Substrate-wide typed registries. Each carries `name` + `description_short`
-- (capped 80 chars) so they project cleanly into v_dr_catalogue / v_shell_catalogue.
-- shell_dr_link binds typed entries to shells (polymorphic via ref_table+ref_id).

CREATE TABLE dr_repo (
    repo_id           INTEGER PRIMARY KEY,
    name              TEXT NOT NULL UNIQUE,
    description_short TEXT NOT NULL CHECK (LENGTH(description_short) <= 100),
    path              TEXT,
    remote            TEXT,
    status            TEXT NOT NULL DEFAULT 'active'
                      CHECK (status IN ('active','deprecated','planned','retired')),
    last_verified     DATE,
    notes             TEXT
);

CREATE TABLE dr_filepath (
    filepath_id       INTEGER PRIMARY KEY,
    name              TEXT NOT NULL,
    description_short TEXT NOT NULL CHECK (LENGTH(description_short) <= 100),
    path              TEXT NOT NULL UNIQUE,
    kind              TEXT NOT NULL CHECK (kind IN ('file','dir')),
    status            TEXT NOT NULL DEFAULT 'active'
                      CHECK (status IN ('active','deprecated','planned','retired')),
    last_verified     DATE,
    notes             TEXT
);

CREATE TABLE dr_router (
    router_id         INTEGER PRIMARY KEY,
    name              TEXT NOT NULL UNIQUE,
    description_short TEXT NOT NULL CHECK (LENGTH(description_short) <= 100),
    file_path         TEXT NOT NULL UNIQUE,
    prefix            TEXT,
    status            TEXT NOT NULL DEFAULT 'active'
                      CHECK (status IN ('active','deprecated','planned','retired')),
    last_verified     DATE,
    notes             TEXT
);

CREATE TABLE dr_api (
    api_id            INTEGER PRIMARY KEY,
    router_id         INTEGER REFERENCES dr_router(router_id),
    name              TEXT NOT NULL,
    description_short TEXT NOT NULL CHECK (LENGTH(description_short) <= 100),
    path              TEXT NOT NULL,
    method            TEXT NOT NULL,
    purpose           TEXT,
    status            TEXT NOT NULL DEFAULT 'active'
                      CHECK (status IN ('active','deprecated','planned','retired')),
    last_verified     DATE,
    notes             TEXT,
    UNIQUE(path, method)
);

CREATE TABLE dr_db (
    db_id         INTEGER PRIMARY KEY,
    table_name    TEXT NOT NULL UNIQUE,
    purpose       TEXT,
    owner_shell   INTEGER REFERENCES shells(shell_id),
    status        TEXT NOT NULL DEFAULT 'active'
                  CHECK (status IN ('active','deprecated','planned','retired')),
    last_verified DATE,
    notes         TEXT
);

CREATE TABLE dr_lib (
    lib_id            INTEGER PRIMARY KEY,
    kind              TEXT NOT NULL CHECK (kind IN ('frontend','backend')),
    name              TEXT NOT NULL,
    description_short TEXT NOT NULL CHECK (LENGTH(description_short) <= 100),
    location          TEXT NOT NULL,
    purpose           TEXT,
    status            TEXT NOT NULL DEFAULT 'active'
                      CHECK (status IN ('active','deprecated','planned','retired')),
    last_verified     DATE,
    notes             TEXT,
    UNIQUE(kind, location)
);

CREATE TABLE dr_dependencies (
    dep_id            INTEGER PRIMARY KEY,
    project           TEXT NOT NULL,
    name              TEXT NOT NULL,
    description_short TEXT NOT NULL CHECK (LENGTH(description_short) <= 100),
    version           TEXT,
    kind              TEXT CHECK (kind IN ('npm','pip','system')),
    notes             TEXT,
    status            TEXT NOT NULL DEFAULT 'active'
                      CHECK (status IN ('active','retired')),
    UNIQUE(project, name)
);

CREATE TABLE dr_services (
    service_id        INTEGER PRIMARY KEY,
    name              TEXT NOT NULL UNIQUE,
    description_short TEXT NOT NULL CHECK (LENGTH(description_short) <= 100),
    kind              TEXT CHECK (kind IN ('api','ui','daemon','watchdog','messenger','other')),
    status            TEXT NOT NULL DEFAULT 'active'
                      CHECK (status IN ('active','inactive','declared-missing','planned','retired')),
    location          TEXT,
    purpose           TEXT,
    last_verified     DATE,
    notes             TEXT
);

CREATE TABLE dr_automations (
    automation_id     INTEGER PRIMARY KEY,
    service_id        INTEGER REFERENCES dr_services(service_id),
    name              TEXT NOT NULL UNIQUE,
    description_short TEXT NOT NULL CHECK (LENGTH(description_short) <= 100),
    trigger_kind      TEXT CHECK (trigger_kind IN ('pm2','cron','systemd','manual','api')),
    schedule          TEXT,
    purpose           TEXT,
    status            TEXT NOT NULL DEFAULT 'active'
                      CHECK (status IN ('active','paused','retired','planned')),
    last_verified     DATE,
    notes             TEXT
);

CREATE TABLE dr_env (
    env_id            INTEGER PRIMARY KEY,
    name              TEXT NOT NULL UNIQUE,
    description_short TEXT NOT NULL CHECK (LENGTH(description_short) <= 100),
    scope             TEXT CHECK (scope IN ('system','shell-rc','dotenv','pm2','runtime')),
    location          TEXT,
    is_secret         INTEGER NOT NULL DEFAULT 0,
    status            TEXT NOT NULL DEFAULT 'active'
                      CHECK (status IN ('active','deprecated','planned','retired')),
    last_verified     DATE,
    notes             TEXT
);

-- Per-shell binding for the catalogue. Polymorphic via (ref_table, ref_id).
CREATE TABLE shell_dr_link (
    link_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    shell_id   INTEGER NOT NULL REFERENCES shells(shell_id),
    ref_table  TEXT    NOT NULL CHECK (ref_table IN
                   ('dr_repo','dr_filepath','dr_router','dr_api','dr_lib',
                    'dr_dependencies','dr_services','dr_automations','dr_env')),
    ref_id     INTEGER NOT NULL,
    role       TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(shell_id, ref_table, ref_id)
);

CREATE TABLE dr_log (
    log_id         INTEGER PRIMARY KEY,
    ref_table      TEXT NOT NULL CHECK (ref_table IN ('dr_api','dr_db','dr_lib','dr_dependencies','dr_services','dr_automations','skills','dr_log')),
    ref_id         INTEGER NOT NULL,
    change_type    TEXT NOT NULL CHECK (change_type IN ('create','update','delete','note')),
    change_summary TEXT NOT NULL CHECK (LENGTH(change_summary) <= 50),
    session_id     TEXT,
    archive_ref    TEXT,
    changed_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- dr_sync_runs — audit log of dr_* catalogue sync invocations. One row per run:
-- a cron full-sync, an in-container FastAPI-startup partial-sync, or a manual
-- `make db-sync`. This is the monitoring surface for catalogue drift — a stale
-- newest run_at means the cron is not firing; a had_error=1 row means a run
-- started but failed (error truncated to 100 chars). A run that never started
-- leaves no row at all: the signal there is the gap, not a row. Rolling-100
-- retention via the trigger below.
CREATE TABLE dr_sync_runs (
    run_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at        TEXT    NOT NULL DEFAULT (datetime('now')),
    trigger_kind  TEXT    NOT NULL CHECK (trigger_kind IN ('cron','startup','manual')),
    surfaces      TEXT,                       -- JSON: {target: {surface: {insert,update} | {error}}}
    total_insert  INTEGER NOT NULL DEFAULT 0,
    total_update  INTEGER NOT NULL DEFAULT 0,
    had_error     INTEGER NOT NULL DEFAULT 0,
    error         TEXT                        -- first/worst error, <=100 chars; NULL if clean
);

CREATE TRIGGER trg_dr_sync_runs_rolling
AFTER INSERT ON dr_sync_runs
BEGIN
  DELETE FROM dr_sync_runs WHERE run_id NOT IN (
    SELECT run_id FROM dr_sync_runs ORDER BY run_id DESC LIMIT 100
  );
END;

-- ── Indexes ───────────────────────────────────────────────────────────────────

CREATE INDEX idx_ui_logs_user   ON app_ui_logs(user_id);
CREATE INDEX idx_ui_logs_ts     ON app_ui_logs(timestamp);
CREATE INDEX idx_flags_parent   ON flags(parent_flag_id);
CREATE INDEX idx_shell_decisions_shell_date ON shell_decisions(shell_id, decision_date);
CREATE INDEX idx_sie_shell_kind_active
    ON shell_identity_entries(shell_id, kind)
    WHERE is_deleted = 0 AND retired_at IS NULL;
CREATE INDEX idx_dr_log_ref     ON dr_log(ref_table, ref_id);
CREATE INDEX idx_dr_log_session ON dr_log(session_id);
CREATE INDEX idx_shell_dr_link_shell ON shell_dr_link(shell_id);

-- ── Views ─────────────────────────────────────────────────────────────────────

-- Substrate-wide catalogue: all typed entries projected to (name, description_short).
-- Lazy-load surface — query when a shell needs the full index of what exists.
CREATE VIEW v_dr_catalogue AS
    SELECT 'dr_repo' AS ref_table, repo_id AS ref_id, name, description_short FROM dr_repo
    UNION ALL
    SELECT 'dr_filepath', filepath_id, name, description_short FROM dr_filepath
    UNION ALL
    SELECT 'dr_router', router_id, name, description_short FROM dr_router
    UNION ALL
    SELECT 'dr_api', api_id, name, description_short FROM dr_api
    UNION ALL
    SELECT 'dr_lib', lib_id, name, description_short FROM dr_lib
    UNION ALL
    SELECT 'dr_dependencies', dep_id, name, description_short FROM dr_dependencies
    UNION ALL
    SELECT 'dr_services', service_id, name, description_short FROM dr_services
    UNION ALL
    SELECT 'dr_automations', automation_id, name, description_short FROM dr_automations
    UNION ALL
    SELECT 'dr_env', env_id, name, description_short FROM dr_env;

-- Per-shell catalogue: filtered through shell_dr_link, includes the shell's role
-- annotation. Lazy-load surface — query when a shell needs the index of what's
-- bound to it specifically.
CREATE VIEW v_shell_catalogue AS
    SELECT l.shell_id, 'dr_repo' AS ref_table, l.ref_id, x.name, x.description_short, l.role
        FROM shell_dr_link l JOIN dr_repo x ON l.ref_id = x.repo_id
        WHERE l.ref_table = 'dr_repo'
    UNION ALL
    SELECT l.shell_id, 'dr_filepath', l.ref_id, x.name, x.description_short, l.role
        FROM shell_dr_link l JOIN dr_filepath x ON l.ref_id = x.filepath_id
        WHERE l.ref_table = 'dr_filepath'
    UNION ALL
    SELECT l.shell_id, 'dr_router', l.ref_id, x.name, x.description_short, l.role
        FROM shell_dr_link l JOIN dr_router x ON l.ref_id = x.router_id
        WHERE l.ref_table = 'dr_router'
    UNION ALL
    SELECT l.shell_id, 'dr_api', l.ref_id, x.name, x.description_short, l.role
        FROM shell_dr_link l JOIN dr_api x ON l.ref_id = x.api_id
        WHERE l.ref_table = 'dr_api'
    UNION ALL
    SELECT l.shell_id, 'dr_lib', l.ref_id, x.name, x.description_short, l.role
        FROM shell_dr_link l JOIN dr_lib x ON l.ref_id = x.lib_id
        WHERE l.ref_table = 'dr_lib'
    UNION ALL
    SELECT l.shell_id, 'dr_dependencies', l.ref_id, x.name, x.description_short, l.role
        FROM shell_dr_link l JOIN dr_dependencies x ON l.ref_id = x.dep_id
        WHERE l.ref_table = 'dr_dependencies'
    UNION ALL
    SELECT l.shell_id, 'dr_services', l.ref_id, x.name, x.description_short, l.role
        FROM shell_dr_link l JOIN dr_services x ON l.ref_id = x.service_id
        WHERE l.ref_table = 'dr_services'
    UNION ALL
    SELECT l.shell_id, 'dr_automations', l.ref_id, x.name, x.description_short, l.role
        FROM shell_dr_link l JOIN dr_automations x ON l.ref_id = x.automation_id
        WHERE l.ref_table = 'dr_automations'
    UNION ALL
    SELECT l.shell_id, 'dr_env', l.ref_id, x.name, x.description_short, l.role
        FROM shell_dr_link l JOIN dr_env x ON l.ref_id = x.env_id
        WHERE l.ref_table = 'dr_env';

-- ── Existing views ────────────────────────────────────────────────────────────

CREATE VIEW flag_schedule AS
WITH RECURSIVE walk(flag_id, parent_flag_id, start_date, created_date,
                    estimated_days, resolved, resolved_date,
                    effective_start, effective_end) AS (
    SELECT
        f.flag_id, f.parent_flag_id, f.start_date, f.created_date,
        f.estimated_days, f.resolved, f.resolved_date,
        COALESCE(
            f.start_date,
            DATE(f.created_date, '+3 days')
        ) AS effective_start,
        CASE
            WHEN f.resolved = 1 THEN f.resolved_date
            WHEN f.estimated_days IS NOT NULL THEN
                DATE(COALESCE(f.start_date, DATE(f.created_date, '+3 days')),
                     '+' || CAST(f.estimated_days AS TEXT) || ' days')
            ELSE NULL
        END AS effective_end
    FROM flags f
    WHERE f.is_deleted = 0
      AND (f.parent_flag_id IS NULL OR f.start_date IS NOT NULL)

    UNION ALL

    SELECT
        f.flag_id, f.parent_flag_id, f.start_date, f.created_date,
        f.estimated_days, f.resolved, f.resolved_date,
        COALESCE(
            CASE WHEN p.resolved = 1 THEN p.resolved_date END,
            p.effective_end,
            DATE(f.created_date, '+3 days')
        ) AS effective_start,
        CASE
            WHEN f.resolved = 1 THEN f.resolved_date
            WHEN f.estimated_days IS NOT NULL THEN
                DATE(
                    COALESCE(
                        CASE WHEN p.resolved = 1 THEN p.resolved_date END,
                        p.effective_end,
                        DATE(f.created_date, '+3 days')
                    ),
                    '+' || CAST(f.estimated_days AS TEXT) || ' days')
            ELSE NULL
        END AS effective_end
    FROM flags f
    JOIN walk p ON p.flag_id = f.parent_flag_id
    WHERE f.is_deleted = 0
      AND f.start_date IS NULL
)
SELECT
    flag_id,
    parent_flag_id,
    start_date,
    estimated_days,
    resolved,
    resolved_date,
    effective_start,
    effective_end,
    CASE
        WHEN resolved = 1 THEN 'resolved'
        WHEN resolved = 0 THEN 'in_progress'   -- Open: active work, regardless of schedule dates
        WHEN effective_start IS NULL THEN 'unscheduled'
        WHEN effective_start <= DATE('now') THEN 'in_progress'
        ELSE 'scheduled'
    END AS status
FROM walk;

-- ── Local environment — hardware + models ────────────────────────────────────
-- A live, programmatically-synced picture of the machines the substrate runs
-- on and the local LLM models installed on them. Same philosophy as the dr_*
-- catalogue: ground truth, refreshed from real state, never hand-maintained.
--   user_hardware     <- collect_hardware.py  (host probe)
--   installed_models  <- model_sync.py        (`ollama list` / `ollama show`)
--
-- `installed_models` is the per-host install inventory — distinct from the
-- agnostic-runtime `models` registry (every model the system *can* use).

CREATE TABLE IF NOT EXISTS user_hardware (
    hardware_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(user_id),
    hostname      TEXT    NOT NULL,
    os            TEXT,                       -- distro / OS pretty name
    kernel        TEXT,
    cpu           TEXT,
    cpu_threads   INTEGER,
    ram_gb        REAL,
    gpu           TEXT,                       -- discrete GPU (the one that matters)
    vram_gb       REAL,
    vram_tier     INTEGER,                    -- bucketed 8/12/24/32/48/128 — for model matching
    disk_free_gb  REAL,
    raw_dump      TEXT,                       -- full probe output, reference
    collected_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    notes         TEXT,
    UNIQUE (user_id, hostname)
);

CREATE INDEX IF NOT EXISTS idx_user_hardware_user ON user_hardware (user_id);

CREATE TABLE IF NOT EXISTS installed_models (
    install_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    hardware_id       INTEGER REFERENCES user_hardware(hardware_id),
    name              TEXT    NOT NULL,       -- runner tag, e.g. qwen2.5-coder:7b
    runner            TEXT    NOT NULL DEFAULT 'ollama',
    provider          TEXT,                   -- Mistral, Alibaba, Google, Meta, ...
    family            TEXT,                   -- coder / general / reasoning / multimodal / embedding
    params            TEXT,                   -- '7.6B'
    size_gb           REAL,                   -- on-disk size
    quantization      TEXT,                   -- Q4_K_M
    context_length    INTEGER,
    min_vram_gb       INTEGER,                -- smallest VRAM tier to run comfortably on GPU
    digest            TEXT,                   -- runner model ID / digest
    status            TEXT    NOT NULL DEFAULT 'installed'
                      CHECK (status IN ('installed','removed')),
    description_short TEXT    CHECK (description_short IS NULL OR LENGTH(description_short) <= 100),
    last_synced       TEXT    NOT NULL DEFAULT (datetime('now')),
    notes             TEXT,
    UNIQUE (hardware_id, name)
);

CREATE INDEX IF NOT EXISTS idx_installed_models_hardware ON installed_models (hardware_id);

-- ── migration tracking ───────────────────────────────────────────────────────
-- One row per applied migration file (see shell_core/migrations/*.sql).
-- migrate.py computes the pending set as migrations/*.sql minus this table;
-- bootstrap.py stamps every shipped migration here right after loading this
-- schema (schema.sql already reflects them). Never edited by hand.
CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_id  TEXT PRIMARY KEY,
    applied_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
