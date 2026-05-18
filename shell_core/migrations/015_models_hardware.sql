-- Local environment tables — user_hardware + models.
--
-- A live, programmatically-synced picture of the machines the substrate runs
-- on and the local LLM models installed on them. Same philosophy as the dr_*
-- catalogue: ground truth, refreshed from real state by collect_hardware.py
-- and model_sync.py, never hand-maintained.
--
--   user_hardware  one row per machine (host probe), FK user_id
--   models         one row per installed model, FK hardware_id
--
-- Schema-only; the sync scripts populate the rows. schema.sql already
-- reflects these tables.

CREATE TABLE IF NOT EXISTS user_hardware (
    hardware_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(user_id),
    hostname      TEXT    NOT NULL,
    os            TEXT,
    kernel        TEXT,
    cpu           TEXT,
    cpu_threads   INTEGER,
    ram_gb        REAL,
    gpu           TEXT,
    vram_gb       REAL,
    vram_tier     INTEGER,
    disk_free_gb  REAL,
    raw_dump      TEXT,
    collected_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    notes         TEXT,
    UNIQUE (user_id, hostname)
);

CREATE INDEX IF NOT EXISTS idx_user_hardware_user ON user_hardware (user_id);

CREATE TABLE IF NOT EXISTS models (
    model_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    hardware_id       INTEGER REFERENCES user_hardware(hardware_id),
    name              TEXT    NOT NULL,
    runner            TEXT    NOT NULL DEFAULT 'ollama',
    provider          TEXT,
    family            TEXT,
    params            TEXT,
    size_gb           REAL,
    quantization      TEXT,
    context_length    INTEGER,
    min_vram_gb       INTEGER,
    digest            TEXT,
    status            TEXT    NOT NULL DEFAULT 'installed'
                      CHECK (status IN ('installed','removed')),
    description_short TEXT    CHECK (description_short IS NULL OR LENGTH(description_short) <= 100),
    last_synced       TEXT    NOT NULL DEFAULT (datetime('now')),
    notes             TEXT,
    UNIQUE (hardware_id, name)
);

CREATE INDEX IF NOT EXISTS idx_models_hardware ON models (hardware_id);
