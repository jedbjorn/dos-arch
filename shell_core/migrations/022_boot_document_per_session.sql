-- 022 — boot_document moves per-session.
--
-- The boot document (the rendered system prompt / typed section catalog) was a
-- per-shell column. But a shell can hold several concurrent chat sessions on
-- different models, and model / dialect / session-id are per session — a
-- per-shell column cannot serve them all (it served whichever session was
-- touched last). So the boot document moves onto chat_sessions: one document
-- per session, rendered at session creation, re-materialized in place on a
-- model switch (substrate decision #123).
--
-- shells.boot_document is left in place, deprecated, until every reader is cut
-- over (boot_document.py + shells.py, slices 2-3); migration 023 drops it.
--
-- Plain SQL: migrate.py owns the transaction and the schema_migrations row.

ALTER TABLE chat_sessions ADD COLUMN boot_document TEXT;
