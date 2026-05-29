-- 053 — repurpose Sys-Admin → Exp-Prime (standardized assistant shell)
--
-- dos-arch shells go non-dev: no coding or substrate administration happens
-- inside the substrate — the sysadmin owns that externally. The resident
-- Sys-Admin shell (shell_id=2) is repurposed IN PLACE into Exp-Prime, the
-- first of a family of standardized shells. Identity-only: task/time, email
-- (IMAP IDLE), and calendar tooling attach later as skills.
--
-- Exp-Prime starts CLEAN — a repurpose produces a fresh assistant, not an
-- inheritor of Sys-Admin's past. This migration carries no history forward:
-- identity is reset and the shell's chat scratch is cleared. (Sys-Admin on a
-- fresh substrate had no decisions/archives/flags/seed to clear; if a sibling
-- install accumulated those, review them before running — this migration does
-- not touch decisions/archives/flags, only identity + chat.)
--
-- Fresh installs get this via the seed assets (assets/shells/exp-prime.md +
-- seed_exp_prime in db_init.py); this migration brings an already-installed
-- substrate to the same state. The retired dev skills (database-migrations,
-- db_patch, skill_management, laws_management, catalogue_sync, file-ops,
-- process-exec, …) stay in the library, just unassigned — non-destructive.
--
-- migrate.py owns the transaction and the schema_migrations row.

-- 1. Re-segment the common baseline: drop two substrate-dev skills an
--    assistant has no use for (both are doc-only — no tools lost). Must run
--    before the INSERT below so the new skill set excludes them.
UPDATE skills SET common = 0 WHERE name IN ('db_backup', 'surface_catalogue');

-- 2. Repurpose the shell identity in place. Targeted by the old shortname so
--    it is robust to shell_id drift (this is shell_id=2). browser_chat,
--    user_id, partner, api_key are intentionally left as-is. api_auth=1 routes
--    it through the credential broker (ToS-correct for a web-facing shell);
--    is_admin=0 because no shell administers the substrate from within.
--    current_state is cleared to NULL — a fresh assistant has no rolling
--    status until it boots and runs bootstrap_interview.
UPDATE shells SET
  display_name  = 'Exp-Prime',
  shortname     = 'exprime',
  role          = 'personal assistant — time, tasks, and correspondence',
  mandate       = 'Assist the operator with time and task management, draft and triage correspondence, and give advice grounded in accumulated context. No coding or substrate administration — that is owned externally by the sysadmin. Email (IMAP IDLE) and calendar-watching capabilities are planned and attach as skills when their tooling lands.',
  connections   = 'Browser-chat + dispatcher-driven; reaches Anthropic through the credential broker (api_auth=1). Capabilities arrive as skills — task/time-management, email-draft, and calendar tooling are not built yet. Until they land, lean on memory (seed, L&S, decisions, flags) and conversation context for advice.

This is a standardized assistant shell, not a dev shell: no schema, migration, skill-catalogue, or API/UI work happens here. Substrate administration is the sysadmin''s job, performed externally from the substrate clone.',
  current_state = NULL,
  api_auth      = 1,
  is_admin      = 0
WHERE shortname = 'sysadmin';

-- 3. Reset the shell's skill set to the re-segmented common baseline
--    (bootstrap_interview, create_flag, create_identity_entry, decision,
--    resolve_flag, shared, surface_flags). The dev skills it carried as
--    Sys-Admin are dropped from the link table only.
DELETE FROM shell_skills
  WHERE shell_id = (SELECT shell_id FROM shells WHERE shortname = 'exprime');

INSERT INTO shell_skills (shell_id, skill_id)
  SELECT (SELECT shell_id FROM shells WHERE shortname = 'exprime'), skill_id
    FROM skills
   WHERE common = 1 AND is_deleted = 0;

-- 4. Clear chat scratch so Exp-Prime starts with no conversational history.
--    Messages first (they reference the session), then the sessions.
DELETE FROM chat_messages
  WHERE shell_id = (SELECT shell_id FROM shells WHERE shortname = 'exprime');
DELETE FROM chat_sessions
  WHERE shell_id = (SELECT shell_id FROM shells WHERE shortname = 'exprime');
