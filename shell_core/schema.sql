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
    theme_accent  TEXT    DEFAULT '#0072FF'
);

-- ── Shells ────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS "shells" (
    shell_id              INTEGER PRIMARY KEY,
    display_name          TEXT    NOT NULL,
    shortname             TEXT,
    owner                 TEXT,
    role                  TEXT,
    mandate               TEXT,
    system_prompt         TEXT    NOT NULL,
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
    api_key_hash          TEXT
);

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
    is_deleted  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE shell_skills (
    shell_skill_id  INTEGER PRIMARY KEY,
    shell_id        INTEGER NOT NULL REFERENCES shells(shell_id),
    skill_id        INTEGER NOT NULL REFERENCES skills(skill_id),
    UNIQUE(shell_id, skill_id)
);

-- ── Chat ──────────────────────────────────────────────────────────────────────

CREATE TABLE chat_sessions (
    chat_session_id    TEXT    PRIMARY KEY,
    shell_id           INTEGER NOT NULL REFERENCES shells(shell_id),
    user_id            INTEGER NOT NULL REFERENCES users(user_id),
    started_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_active        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_active          INTEGER NOT NULL DEFAULT 1,
    total_tokens       INTEGER NOT NULL DEFAULT 0,
    token_warning_sent INTEGER NOT NULL DEFAULT 0
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
    is_deleted  INTEGER NOT NULL DEFAULT 0
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

-- ── current_state length cap (rolling status, not a log) ────────────────────
-- Hard cap at 280 chars (~2 lines, ~70 tokens). current_state describes what
-- the shell is working on now and what comes next — NOT a session log. It is
-- rolling: writes overwrite. Identity bodies belong in seed/L&S; logs belong
-- in shell_memory_archives. Triggers below abort writes that exceed the cap.

CREATE TRIGGER trg_current_state_cap_insert
BEFORE INSERT ON shells
WHEN NEW.current_state IS NOT NULL AND length(NEW.current_state) > 280
BEGIN
  SELECT RAISE(ABORT, 'current_state exceeds 280 chars — rolling status, not a log; trim to "now / next"');
END;

CREATE TRIGGER trg_current_state_cap_update
BEFORE UPDATE OF current_state ON shells
WHEN NEW.current_state IS NOT NULL AND length(NEW.current_state) > 280
BEGIN
  SELECT RAISE(ABORT, 'current_state exceeds 280 chars — rolling status, not a log; trim to "now / next"');
END;

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
        WHEN effective_start IS NULL THEN 'unscheduled'
        WHEN effective_start <= DATE('now') THEN 'in_progress'
        ELSE 'scheduled'
    END AS status
FROM walk;
