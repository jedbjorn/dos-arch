-- 045 — add 'ollama_cloud' to the models.provider CHECK and register one
-- smoke-test cloud row.
--
-- Ollama Cloud (https://ollama.com) speaks the same native /api/chat
-- protocol as a self-hosted Ollama daemon — the only differences are the
-- host (ollama.com instead of localhost:11434) and an Authorization: Bearer
-- header carrying an API key. The existing OllamaAdapter is therefore close
-- to working as-is; this migration unblocks the registry side so a cloud
-- row can land at provider='ollama_cloud' (kept distinct from the local
-- self-hosted 'local' provider so cost/limit/sync semantics can diverge
-- cleanly downstream).
--
-- SQLite has no ALTER … CHECK — rebuild the table. Same dance as migration
-- 035: drop dependent views, rebuild, copy, swap, recreate.
--
-- This migration:
--   1. extends the provider CHECK with 'ollama_cloud';
--   2. inserts one smoke-test row (gpt-oss:120b-cloud) so the picker has a
--      target the moment the OllamaCloudAdapter is registered. The bulk
--      catalog sync lands in a follow-up (PR 2).

DROP VIEW IF EXISTS v_cache_health;

CREATE TABLE models_new (
    model_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT    NOT NULL UNIQUE,
    display_name        TEXT,
    provider            TEXT    NOT NULL
                        CHECK (provider IN ('anthropic','openai','google','local','ollama_cloud')),
    endpoint            TEXT,
    auth_ref            TEXT,
    tool_dialect        TEXT    NOT NULL DEFAULT 'anthropic'
                        CHECK (tool_dialect IN ('anthropic','openai','parsed')),
    context_window      INTEGER,
    max_output          INTEGER,
    capability_tags     TEXT,
    locality            TEXT    NOT NULL DEFAULT 'remote'
                        CHECK (locality IN ('remote','local')),
    vram_estimate_gb    INTEGER,
    version             TEXT,
    source_url          TEXT,
    cost_input          REAL,
    cost_output         REAL,
    cost_cache_read     REAL,
    cost_cache_write    REAL,
    status              TEXT    NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active','inactive')),
    supports_tools           INTEGER,
    accepts_substrate_system INTEGER,
    last_verified       TEXT
);

INSERT INTO models_new (
    model_id, name, display_name, provider, endpoint, auth_ref, tool_dialect,
    context_window, max_output, capability_tags, locality, vram_estimate_gb,
    version, source_url, cost_input, cost_output, cost_cache_read,
    cost_cache_write, status, supports_tools, accepts_substrate_system,
    last_verified)
SELECT
    model_id, name, display_name, provider, endpoint, auth_ref, tool_dialect,
    context_window, max_output, capability_tags, locality, vram_estimate_gb,
    version, source_url, cost_input, cost_output, cost_cache_read,
    cost_cache_write, status, supports_tools, accepts_substrate_system,
    last_verified
FROM models;

DROP TABLE models;
ALTER TABLE models_new RENAME TO models;

CREATE INDEX idx_models_status ON models (status);

-- Smoke-test row — one cloud model the picker can land on the moment the
-- adapter ships. Cloud models are curated and tool-capable by definition;
-- supports_tools and accepts_substrate_system are hardcoded 1 (same
-- convention as the Anthropic/OpenAI rows). The bulk catalog comes from the
-- cloud-sync script (PR 2); this row is just enough to verify end-to-end.
INSERT INTO models (
    name, display_name, provider, endpoint, auth_ref, tool_dialect,
    context_window, max_output, locality, status,
    supports_tools, accepts_substrate_system)
VALUES (
    'gpt-oss:120b-cloud', 'gpt-oss 120B (cloud)', 'ollama_cloud',
    'https://ollama.com', 'OLLAMA_CLOUD_API_KEY', 'openai',
    131072, 4096, 'remote', 'active',
    1, 1);

-- Recreate v_cache_health verbatim — body unchanged from migration 035.
CREATE VIEW v_cache_health AS
SELECT
  cs.chat_session_id,
  cs.shell_id,
  m.name     AS model_name,
  m.provider AS provider,
  COUNT(*)                               AS turns,
  SUM(COALESCE(cm.cache_hit_tokens,  0)) AS cache_hit_tokens,
  SUM(COALESCE(cm.cache_miss_tokens, 0)) AS cache_miss_tokens,
  CAST(SUM(COALESCE(cm.cache_hit_tokens, 0)) AS REAL)
    / NULLIF(SUM(COALESCE(cm.cache_hit_tokens,  0)
                 + COALESCE(cm.cache_miss_tokens, 0)), 0) AS hit_rate
FROM chat_sessions cs
JOIN chat_messages cm ON cm.chat_session_id = cs.chat_session_id
JOIN models        m  ON m.model_id = cs.model_id
WHERE cm.direction = 'outbound'
  AND COALESCE(cm.is_deleted, 0) = 0
  AND (cm.cache_hit_tokens IS NOT NULL OR cm.cache_miss_tokens IS NOT NULL)
GROUP BY cs.chat_session_id;
