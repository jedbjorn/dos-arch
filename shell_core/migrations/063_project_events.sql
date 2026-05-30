-- 063 — project_events: append-only, project-scoped, event-only audit log.
--
-- Second step of the data-isolation model (docs/specs/auth-provisioning.md →
-- "Logging — project_events, event-only"; CC-108). Flags are its first writer
-- (062 gave them the project spine); other project actions wire in later.
--
-- EVENT-ONLY by design: it records the verb, the actor, and the time — never
-- the data (no field values, no note bodies). That is what lets it be
-- uniformly team-visible with no per-entity filtering: a private flag's
-- "updated by X" leaks nothing about the flag's contents. Rows are written
-- app-layer in the SAME transaction as the action (not via triggers — a
-- trigger can neither see the session actor nor name the semantic action).
--
-- Plain SQL: migrate.py owns the transaction and the schema_migrations row.

CREATE TABLE project_events (
  event_id       INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id     INTEGER NOT NULL REFERENCES projects(project_id),
  entity_type    TEXT    NOT NULL,                 -- 'flag' (first); extensible
  entity_id      INTEGER NOT NULL,                 -- the acted-on row's id
  action         TEXT    NOT NULL CHECK(action IN
                   ('created','updated','resolved','reopened','deleted')),
  actor_user_id  INTEGER REFERENCES users(user_id),   -- who acted (session user)
  actor_shell_id INTEGER REFERENCES shells(shell_id), -- and/or the acting shell
  created_at     TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_project_events_project ON project_events(project_id);
CREATE INDEX idx_project_events_entity  ON project_events(entity_type, entity_id);
