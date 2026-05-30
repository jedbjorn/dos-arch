-- 064 — flags.project_id NOT NULL: physical formalization of the app-layer rule.
--
-- Final step of the flags data-isolation layer (docs/specs/data-isolation.md,
-- CC-108). project_id has been *required at create* since 062 — create_flag
-- resolves it or returns 422 — so the column has been logically NOT NULL for a
-- while; this makes the constraint physical so no future code path can insert a
-- project-less (and therefore unscoped, invisible) flag.
--
-- SQLite cannot ALTER a column to NOT NULL, so this is the standard table
-- rebuild: create-new / copy / drop / rename (SQLite docs §"Making Other Kinds
-- Of Table Schema Changes"). migrate.py runs it in one transaction with
-- foreign_keys OFF (the connection default), so the self-referential
-- parent_flag_id FK and the drop/rename are safe.
--
-- The `flag_schedule` view reads flags, so it is dropped before the rebuild and
-- recreated verbatim after (a view over a dropped table blocks the rename).
-- Verified before authoring: 0 rows (incl. soft-deleted) have a NULL project_id,
-- so the copy cannot violate the new constraint.

DROP VIEW flag_schedule;

CREATE TABLE flags_new (
    flag_id            INTEGER PRIMARY KEY,
    display_name       TEXT,
    priority           TEXT    NOT NULL CHECK(priority IN ('High','Medium','Low')),
    description        TEXT,
    created_date       DATE    NOT NULL,
    resolved_date      DATE,
    resolved           INTEGER NOT NULL DEFAULT 0,
    shell_id           INTEGER REFERENCES shells(shell_id),
    start_date         DATE,
    resolution_notes   TEXT,
    is_deleted         INTEGER NOT NULL DEFAULT 0,
    parent_flag_id     INTEGER REFERENCES flags(flag_id),
    estimated_days     REAL,
    project_id         INTEGER NOT NULL REFERENCES projects(project_id),
    created_by_user_id INTEGER REFERENCES users(user_id),
    team_flag          INTEGER NOT NULL DEFAULT 1
);

INSERT INTO flags_new
  SELECT flag_id, display_name, priority, description, created_date,
         resolved_date, resolved, shell_id, start_date, resolution_notes,
         is_deleted, parent_flag_id, estimated_days,
         project_id, created_by_user_id, team_flag
    FROM flags;

DROP TABLE flags;
ALTER TABLE flags_new RENAME TO flags;

CREATE INDEX idx_flags_parent  ON flags(parent_flag_id);
CREATE INDEX idx_flags_project ON flags(project_id);

-- Recreate flag_schedule verbatim (unchanged from its pre-064 definition).
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
