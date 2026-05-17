-- flag_schedule.status ignored `resolved`: an Open flag (resolved=0) with a
-- future effective_start reported status='scheduled' — simultaneously Open
-- and not-yet-effective, which is logically inconsistent (Sys-Admin E2E
-- gap 6). The view now short-circuits on resolved: Resolved → 'resolved',
-- Open → 'in_progress' (active work, schedule dates aside). Tracking (2)
-- still falls through to the date-driven branches — Tracking IS the
-- scheduled-for-later state. SQLite has no ALTER VIEW; drop + recreate.

DROP VIEW IF EXISTS flag_schedule;

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
