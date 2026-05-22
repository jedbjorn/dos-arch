-- 024 — cache observability.
--
-- The dispatcher already caches the boot document (Block 1-2) on every
-- provider, but no cache telemetry is captured: each adapter's
-- parse_response read input/output tokens and discarded the provider's
-- cache-hit fields. Without them you cannot tell whether caching is working
-- on a given session / model — a misconfigured row misses every cache
-- silently.
--
-- Two columns on chat_messages carry the normalized counts, written on the
-- outbound (reply) row alongside `tokens` by POST /chat/reply:
--
--   cache_hit_tokens  — input tokens served from a cache read (cheap / free).
--   cache_miss_tokens — input tokens processed fresh (cache writes included).
--
-- Both nullable: Ollama's /api/chat reports no cache counts, so local-model
-- rows leave them NULL. v_cache_health rolls the counts up per session.
--
-- Plain SQL: migrate.py owns the transaction and the schema_migrations row.

ALTER TABLE chat_messages ADD COLUMN cache_hit_tokens  INTEGER;
ALTER TABLE chat_messages ADD COLUMN cache_miss_tokens INTEGER;

-- Per-session cache-hit roll-up — surfaces a model silently missing every
-- cache. Counts live on the outbound (reply) row; rows without cache data
-- (Ollama, pre-024, warning/clear messages) are excluded so `turns` counts
-- only real model turns.
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
