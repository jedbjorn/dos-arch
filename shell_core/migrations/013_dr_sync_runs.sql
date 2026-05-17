-- dr_sync_runs — audit log of dr_* catalogue sync invocations. Adds the run
-- log + rolling-100 retention trigger to existing DBs. New bootstraps get it
-- straight from schema.sql; this file carries the same DDL for live DBs.
--
-- One row per run (cron full-sync, FastAPI-startup partial-sync, manual
-- db-sync). The monitoring surface for catalogue drift: a stale newest
-- run_at means the cron is not firing; a had_error=1 row means a run
-- started but failed. A run that never started leaves no row — the signal
-- there is the gap, not a row.
CREATE TABLE IF NOT EXISTS dr_sync_runs (
    run_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at        TEXT    NOT NULL DEFAULT (datetime('now')),
    trigger_kind  TEXT    NOT NULL CHECK (trigger_kind IN ('cron','startup','manual')),
    surfaces      TEXT,
    total_insert  INTEGER NOT NULL DEFAULT 0,
    total_update  INTEGER NOT NULL DEFAULT 0,
    had_error     INTEGER NOT NULL DEFAULT 0,
    error         TEXT
);

CREATE TRIGGER IF NOT EXISTS trg_dr_sync_runs_rolling
AFTER INSERT ON dr_sync_runs
BEGIN
  DELETE FROM dr_sync_runs WHERE run_id NOT IN (
    SELECT run_id FROM dr_sync_runs ORDER BY run_id DESC LIMIT 100
  );
END;
