-- 058 — core data model: project membership + contacts/emails/events/notes.
--
-- Implements docs/core-data-model.md (supersedes CC-090). The project is the
-- spine: access flows user → project; correspondence and events file under a
-- contact's default project; everything that isn't a project or a user points
-- at one.
--
-- This migration BUILDS the new surfaces. The mesh it replaces
-- (project_shells, shell_groups, shell_group_members, project_groups) is
-- dropped in 059 — after the render chain is repointed off project_shells.
--
--   * user_projects   — user ↔ project membership (N:M); role owner|member.
--                       A shell inherits its projects from its user; there is
--                       no per-shell scoping. Replaces the whole shell-group
--                       mesh with one join table.
--   * contacts        — external people + geocoded location; N:M to projects
--                       via contact_projects, plus an editable default_project.
--   * emails          — correspondence, N:1 contact; project_id seeded from
--                       the contact default at creation, then overridable.
--   * events          — calendar events + location; N:M to contacts, users,
--                       and projects. The "default" project is the is_primary
--                       row of event_projects (no separate FK column).
--   * notes           — unified annotation feed; exclusive arc (typed nullable
--                       FKs + a CHECK enforcing the valid target per kind).
--
-- Location columns are inlined per-entity (contacts, events) for now; a shared
-- locations table only pays off if venues start repeating (deferred).
--
-- Plain SQL: migrate.py owns the transaction and the schema_migrations row.

-- ── Project membership (user-scoped, N:M) ───────────────────────────────────
CREATE TABLE user_projects (
  user_project_id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    INTEGER NOT NULL REFERENCES users(user_id),
  project_id INTEGER NOT NULL REFERENCES projects(project_id),
  role       TEXT NOT NULL DEFAULT 'member'
               CHECK(role IN ('owner','member')),   -- creator=owner; multi-owner allowed
  added_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  is_deleted INTEGER NOT NULL DEFAULT 0,
  UNIQUE (user_id, project_id)
);
CREATE INDEX idx_user_projects_user    ON user_projects(user_id);
CREATE INDEX idx_user_projects_project ON user_projects(project_id);

-- Backfill: derive membership from any pre-existing project_shells intent,
-- mapping each shell to its owning user. Live DB has 0 mesh rows, so this is a
-- clean start in practice — written for correctness on any populated clone.
-- INSERT OR IGNORE collapses multiple shells of the same user on one project
-- to a single membership row (UNIQUE user_id,project_id); role lands 'member'.
INSERT OR IGNORE INTO user_projects (user_id, project_id, is_deleted)
SELECT s.user_id, ps.project_id, 0
  FROM project_shells ps
  JOIN shells s ON s.shell_id = ps.shell_id
 WHERE ps.is_deleted = 0
   AND s.user_id IS NOT NULL;

-- ── Contacts (external people + geocoded location) ───────────────────────────
CREATE TABLE contacts (
  contact_id INTEGER PRIMARY KEY AUTOINCREMENT,
  name       TEXT NOT NULL,
  email      TEXT,
  phone      TEXT,
  -- structured / geocoded location (not raw text):
  formatted_address TEXT,
  locality   TEXT,
  region     TEXT,
  country    TEXT,
  postal_code TEXT,
  lat        REAL,
  lng        REAL,
  default_project_id INTEGER REFERENCES projects(project_id),
  is_deleted INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE contact_projects (
  contact_project_id INTEGER PRIMARY KEY AUTOINCREMENT,
  contact_id INTEGER NOT NULL REFERENCES contacts(contact_id),
  project_id INTEGER NOT NULL REFERENCES projects(project_id),
  is_deleted INTEGER NOT NULL DEFAULT 0,
  UNIQUE (contact_id, project_id)
);
CREATE INDEX idx_contact_projects_project ON contact_projects(project_id);

-- ── Emails (correspondence, N:1 contact, re-fileable project) ────────────────
CREATE TABLE emails (
  email_id   INTEGER PRIMARY KEY AUTOINCREMENT,
  contact_id INTEGER NOT NULL REFERENCES contacts(contact_id),
  project_id INTEGER REFERENCES projects(project_id),  -- seeded from contact default, editable
  direction  TEXT CHECK(direction IN ('inbound','outbound')),
  subject    TEXT,
  body       TEXT,
  occurred_at TIMESTAMP,                 -- sent / received time
  message_id TEXT,                       -- optional: real mail-sync later
  thread_id  TEXT,
  is_deleted INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_emails_contact ON emails(contact_id);
CREATE INDEX idx_emails_project ON emails(project_id);

-- ── Events (calendar + location), N:M to contacts/users/projects ─────────────
CREATE TABLE events (
  event_id   INTEGER PRIMARY KEY AUTOINCREMENT,
  title      TEXT NOT NULL,
  start_at   TIMESTAMP,
  end_at     TIMESTAMP,
  formatted_address TEXT, locality TEXT, region TEXT,
  country TEXT, postal_code TEXT, lat REAL, lng REAL,
  is_deleted INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE event_contacts (
  event_id   INTEGER NOT NULL REFERENCES events(event_id),
  contact_id INTEGER NOT NULL REFERENCES contacts(contact_id),
  UNIQUE (event_id, contact_id)
);
CREATE INDEX idx_event_contacts_contact ON event_contacts(contact_id);

CREATE TABLE event_users (
  event_id INTEGER NOT NULL REFERENCES events(event_id),
  user_id  INTEGER NOT NULL REFERENCES users(user_id),
  UNIQUE (event_id, user_id)
);
CREATE INDEX idx_event_users_user ON event_users(user_id);

CREATE TABLE event_projects (
  event_id   INTEGER NOT NULL REFERENCES events(event_id),
  project_id INTEGER NOT NULL REFERENCES projects(project_id),
  is_primary INTEGER NOT NULL DEFAULT 0,   -- the editable "default" project
  UNIQUE (event_id, project_id)
);
CREATE INDEX idx_event_projects_project ON event_projects(project_id);

-- ── Notes (unified annotation feed; exclusive arc) ───────────────────────────
-- One table, typed nullable FK targets, a CHECK enforcing the valid target per
-- kind (matrix in the spec). author_user_id is who wrote it; the target user_id
-- is the subject of a note *about* a user — the two are distinct columns.
CREATE TABLE notes (
  note_id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind    TEXT NOT NULL CHECK(kind IN
            ('note','document','meeting_prep','meeting_result')),
  body    TEXT,
  author_user_id INTEGER REFERENCES users(user_id),
  -- target arc (kind-constrained per matrix):
  contact_id INTEGER REFERENCES contacts(contact_id),
  event_id   INTEGER REFERENCES events(event_id),
  project_id INTEGER REFERENCES projects(project_id),
  user_id    INTEGER REFERENCES users(user_id),
  -- document kind only:
  doc_url  TEXT, doc_mime TEXT, doc_size INTEGER,
  is_deleted INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK (
       (kind='note' AND
          (contact_id IS NOT NULL) + (event_id IS NOT NULL)
        + (project_id IS NOT NULL) + (user_id IS NOT NULL) = 1)
    OR (kind='document' AND user_id IS NULL AND contact_id IS NULL AND
          (event_id IS NOT NULL) + (project_id IS NOT NULL) = 1)
    OR (kind IN ('meeting_prep','meeting_result') AND event_id IS NOT NULL
          AND contact_id IS NULL AND project_id IS NULL AND user_id IS NULL)
  )
);
CREATE INDEX idx_notes_contact ON notes(contact_id);
CREATE INDEX idx_notes_event   ON notes(event_id);
CREATE INDEX idx_notes_project ON notes(project_id);
CREATE INDEX idx_notes_user    ON notes(user_id);
