-- 035 — classify whether a model's template lets the substrate boot prompt
-- through when tools are also passed.
--
-- Background: PR #100 (migration 034) added `supports_tools` so phi3-class
-- models — whose Ollama template lacks the `tools` capability — are hidden
-- from the picker. That fixed Ollama HTTP 400 *"does not support tools"*.
--
-- Hermes3 surfaced a second, subtler failure: its template branches as
-- `{{ if .Tools }} ... {{ else if .System }} ... {{ end }}` — when tools
-- are present, the user-supplied System content is silently dropped before
-- the model sees it. The model replies, Ollama returns no error, dispatch
-- posts the reply — but the substrate boot prompt never arrived. The
-- shell appears to work and is actually identity-less.
--
-- Detection is template-side and free: `/api/show.template` is a string;
-- the model_sync classifier regexes it for the `if .Tools ... else if
-- .System` pattern. No probe call, no VRAM hit. Manual flip exists in the
-- picker UI for templates the regex doesn't catch — that route also feeds
-- the (future) agents surface, where these models still earn their keep.
--
-- This migration:
--   1. drops NOT NULL on `supports_tools` — NULL now means "not yet
--      classified" and the classifier re-probes on every watch tick until
--      the field is set;
--   2. resets local rows with `supports_tools=0` to NULL so the new
--      classifier (which reads /api/show.capabilities — same source as 034
--      but now also writes accepts_substrate_system in the same pass)
--      re-derives both fields together;
--   3. adds `accepts_substrate_system INTEGER NULL` — NULL=unknown, 1=
--      template emits System with Tools, 0=template drops System (hermes);
--   4. marks cloud rows accepts_substrate_system=1 — every active
--      provider we ship (Anthropic, OpenAI, Google) accepts a system
--      prompt alongside tools.

-- SQLite has no DROP NOT NULL — rebuild the table. Views that JOIN models
-- (only v_cache_health today) reference the *table*, not its rows, so they
-- become invalid the instant we DROP TABLE; recreate them after the swap.
DROP VIEW IF EXISTS v_cache_health;

CREATE TABLE models_new (
    model_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT    NOT NULL UNIQUE,
    display_name        TEXT,
    provider            TEXT    NOT NULL
                        CHECK (provider IN ('anthropic','openai','google','local')),
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
    supports_tools           INTEGER,    -- NULL = unclassified
    accepts_substrate_system INTEGER,    -- NULL = unclassified
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
    cost_cache_write, status,
    -- Local rows with supports_tools=0 (the migration-034 sentinel before
    -- modelsync re-derived) are reset to NULL so the new classifier writes
    -- both fields together; verified 1s stay.
    CASE WHEN provider='local' AND supports_tools=0 THEN NULL
         ELSE supports_tools END,
    -- Cloud rows accept system+tools by definition; local rows wait for
    -- the classifier to read the template.
    CASE WHEN provider IN ('anthropic','openai','google') THEN 1
         ELSE NULL END,
    last_verified
FROM models;

DROP TABLE models;
ALTER TABLE models_new RENAME TO models;

CREATE INDEX idx_models_status ON models (status);

-- Recreate the view dropped above. Body verbatim from the original definition.
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
