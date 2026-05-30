-- 062 — flags gain a project spine + seed the System project.
--
-- First concrete step of the three-class data-isolation model
-- (docs/specs/auth-provisioning.md → "Data isolation"; CC-108). The project is
-- the spine: a flag belongs to a project, is team-visible by default, and
-- records who raised it. This migration lands the FLAGS half of that schema and
-- seeds the first project so the model has something real to scope.
--
--   * flags.project_id         — the project a flag is filed under (the spine).
--                                Nullable for now: existing create paths don't
--                                supply it yet. The router slice (visibility +
--                                NOT NULL enforcement) is the next step; the
--                                live DB has 0 flags so there is nothing to
--                                strand in the meantime.
--   * flags.created_by_user_id — who raised it (the access axis for a private
--                                flag). shell_id is demoted to provenance only.
--   * flags.team_flag          — 1 = whole project team sees it AND any member
--                                may act on it (default); 0 = creator-only.
--
-- project_events (the append-only, event-only audit log flags will write to)
-- lands with the router slice that produces its first writer — an empty
-- audit table with no writer would be premature here.
--
-- Plain SQL: migrate.py owns the transaction and the schema_migrations row.

-- ── flags: project spine + creator + privacy bit ────────────────────────────
ALTER TABLE flags ADD COLUMN project_id         INTEGER REFERENCES projects(project_id);
ALTER TABLE flags ADD COLUMN created_by_user_id INTEGER REFERENCES users(user_id);
ALTER TABLE flags ADD COLUMN team_flag          INTEGER NOT NULL DEFAULT 1;
CREATE INDEX idx_flags_project ON flags(project_id);

-- ── System project (the substrate itself) ───────────────────────────────────
-- The platform's own work: infrastructure, auth, schema, the shell fleet.
-- shortname is the stable key the seeds below resolve against (project_id is
-- AUTOINCREMENT, so it can't be hardcoded portably).
INSERT INTO projects (shortname, title, purpose, status)
VALUES (
  'system',
  'System',
  'Substrate-level work: the dos-arch platform itself — infrastructure, auth, schema, and the shell fleet.',
  'active'
);

-- ── Membership: Jed (user 1) owns the System project ─────────────────────────
-- Membership is user-level (project_shells was dropped in #160). Exp-Prime
-- (shell 2) is owned by user 1, so this single owner row covers both "Jed" and
-- "Exp-Prime": the shell inherits its user's projects, and its profile card is
-- System-visible because its owner is a member.
INSERT INTO user_projects (user_id, project_id, role)
SELECT 1, project_id, 'owner' FROM projects WHERE shortname = 'system';

-- ── Default flag for the System project ──────────────────────────────────────
-- A standing, team-visible anchor establishing the project→flag link under the
-- isolation model. Tracking (resolved=2) — a fixture, not active blocking work.
-- created_by_user_id = Jed; shell_id = 2 (Exp-Prime) as provenance only.
INSERT INTO flags (display_name, priority, description, created_date,
                   resolved, shell_id, project_id, created_by_user_id, team_flag)
SELECT
  'Default Flag',
  'Low',
  '[System] Default flag for the System project — the anchor establishing the project→flag link under the three-class isolation model.',
  date('now'),
  2,                 -- Tracking: a standing fixture, not a blocker
  2,                 -- provenance: raised by Exp-Prime
  1,                 -- created_by: Jed (user 1)
  1,                 -- team_flag: visible to the whole System team
  project_id
FROM projects WHERE shortname = 'system';
