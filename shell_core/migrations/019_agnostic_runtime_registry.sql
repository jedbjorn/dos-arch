-- CC-50 (A1) PR1 — the agnostic-runtime registry foundation.
--
-- Three tables + one column, all additive (agnostic-runtime §4.1-§4.3):
--   models       every model the system *can* use — provider/dialect/cost
--   tools        provider-agnostic tooling-as-data (mirrors `skills`)
--   shell_tools  per-shell tool grants (mirrors `shell_skills`)
--   chat_sessions.model_id  the conversation's model
--
-- DDL only. The seed rows — the model registry, the api_* tools, and the
-- per-shell grants — come from db_init.seed_models / seed_tools: run by
-- `make bootstrap` on a fresh DB, and once by hand on a migrated one
-- (both seeders are INSERT-missing-only, so re-running is safe).

CREATE TABLE tools (
    tool_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    description TEXT,
    kind        TEXT    NOT NULL DEFAULT 'builtin'
                CHECK (kind IN ('builtin','script','mcp')),
    spec        TEXT,
    handler     TEXT,
    status      TEXT    NOT NULL DEFAULT 'active'
                CHECK (status IN ('active','inactive'))
);

CREATE TABLE shell_tools (
    shell_tool_id INTEGER PRIMARY KEY,
    shell_id      INTEGER NOT NULL REFERENCES shells(shell_id),
    tool_id       INTEGER NOT NULL REFERENCES tools(tool_id),
    UNIQUE (shell_id, tool_id)
);

CREATE TABLE models (
    model_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT    NOT NULL UNIQUE,
    display_name     TEXT,
    provider         TEXT    NOT NULL
                     CHECK (provider IN ('anthropic','openai','google','local')),
    endpoint         TEXT,
    auth_ref         TEXT,
    tool_dialect     TEXT    NOT NULL DEFAULT 'anthropic'
                     CHECK (tool_dialect IN ('anthropic','openai','parsed')),
    context_window   INTEGER,
    max_output       INTEGER,
    capability_tags  TEXT,
    locality         TEXT    NOT NULL DEFAULT 'remote'
                     CHECK (locality IN ('remote','local')),
    vram_estimate_gb INTEGER,
    version          TEXT,
    source_url       TEXT,
    cost_input       REAL,
    cost_output      REAL,
    cost_cache_read  REAL,
    cost_cache_write REAL,
    status           TEXT    NOT NULL DEFAULT 'active'
                     CHECK (status IN ('active','inactive')),
    last_verified    TEXT
);

CREATE INDEX idx_models_status ON models (status);

-- model_id is nullable: a session with no model set falls back to the
-- dispatcher's default. No backfill — the dispatcher resolves NULL per turn.
ALTER TABLE chat_sessions ADD COLUMN model_id INTEGER REFERENCES models(model_id);
