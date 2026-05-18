-- CC-47 — dispatcher port: schema foundation.
--
-- Prepares the substrate for the browser-chat dispatcher (ExpLive's
-- dispatch_live.py, ported). Four deltas:
--
--   shells.system_prompt -> additional_prompt
--       One column, renamed. It is Block 1 of the boot document — the
--       per-shell operating protocol; "additional_prompt" is ExpLive's
--       name for the same thing. The code rename (run.py, db_init.py,
--       shells.py) lands in the same PR. dos-arch decision #108.
--
--   shells.boot_document  (new, nullable TEXT)
--       Materialized boot document — the rendered stable payload
--       (Blocks 1-2), kept fresh by the API identity-write paths. The
--       dispatcher reads it in one SELECT instead of recomposing it
--       per turn. agnostic-runtime spec §5.1; dos-arch decision #107.
--
--   chat_sessions.turn_in_flight_at / turn_in_flight_message_id  (new)
--       The dispatcher's visible per-session lock — one turn per
--       conversation at a time.
--
--   users.chat_history_window  (new, nullable INTEGER)
--       Per-user rolling-window size for replayed history; NULL falls
--       back to the dispatcher default (25).
--
-- All additive or in-place; no backfill. additional_prompt keeps the
-- NOT NULL constraint inherited from system_prompt.

ALTER TABLE shells RENAME COLUMN system_prompt TO additional_prompt;
ALTER TABLE shells ADD COLUMN boot_document TEXT;

ALTER TABLE chat_sessions ADD COLUMN turn_in_flight_at         TIMESTAMP;
ALTER TABLE chat_sessions ADD COLUMN turn_in_flight_message_id INTEGER REFERENCES chat_messages(message_id);

ALTER TABLE users ADD COLUMN chat_history_window INTEGER;
