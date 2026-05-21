-- 020 — render-chain schema: soft caps, tool dialect, structured skill triggers.
--
-- Coordinated schema changes for the shell-prompt-renderer spec (§04, §05,
-- §07, §09):
--
--   soft caps      Drop the body-length / current_state-length ABORT
--                  triggers. Length becomes a rendered ~target the shell
--                  aims at, not a hard wall whose ABORT costs a retry. The
--                  count caps (trg_sie_cap_seed/lns, 10/20) stay — those are
--                  curation, not tokens. The API mirrors of these length
--                  caps are removed in the same PR (api/routers/shells.py);
--                  the rendered soft-cap instruction lands with the
--                  section-catalog rebuild.
--
--   tool dialect   tools.parsed_example holds a hand-authored invocation
--                  example for parsed-dialect (local 8B) shells; NULL for
--                  anthropic / openai shells, which never render it.
--
--   skill triggers skills gain a structured two-trigger surface —
--                  trigger_explicit (the --name token), trigger_keywords
--                  (comma-separated list), trigger_use_when (one-sentence
--                  disambiguator). trigger_explicit is backfilled here and
--                  defaulted on future inserts; keywords / use_when stay
--                  NULL, backfilled lazily through the skill_management
--                  skill as each skill is next touched.
--
--   identity trim  shell_identity_entries.priority / pin — trim-ordering and
--                  never-drop flags for when a rendered section exceeds
--                  budget (§09.2). pin defaults 0; whether lineage-seed
--                  entries default pin=1 is a spec open question, left to
--                  application logic — not baked here.
--
-- The dr_* description_short / change_summary CHECKs are table-level; dropping
-- them needs a table rebuild — deferred to a follow-up migration (§09.4).
--
-- Plain SQL: migrate.py owns the transaction and the schema_migrations row.

-- ── soft caps: drop the length-ABORT triggers ───────────────────────────────
DROP TRIGGER IF EXISTS trg_sie_body_cap_seed;
DROP TRIGGER IF EXISTS trg_sie_body_cap_lns;
DROP TRIGGER IF EXISTS trg_current_state_cap_insert;
DROP TRIGGER IF EXISTS trg_current_state_cap_update;

-- ── tool dialect: parsed-dialect invocation example ─────────────────────────
ALTER TABLE tools ADD COLUMN parsed_example TEXT;

-- ── identity entries: trim priority + never-drop pin ────────────────────────
ALTER TABLE shell_identity_entries
  ADD COLUMN priority TEXT CHECK (priority IN ('H','M','L')) DEFAULT 'M';
ALTER TABLE shell_identity_entries
  ADD COLUMN pin INTEGER NOT NULL DEFAULT 0;

-- ── skills: structured two-trigger surface ──────────────────────────────────
ALTER TABLE skills ADD COLUMN trigger_explicit TEXT;
ALTER TABLE skills ADD COLUMN trigger_keywords TEXT;
ALTER TABLE skills ADD COLUMN trigger_use_when TEXT;

-- backfill the explicit --name token for every existing live skill
UPDATE skills SET trigger_explicit = '--' || name
WHERE trigger_explicit IS NULL AND is_deleted = 0;

-- default the explicit token on every future insert — overridable: set
-- trigger_explicit explicitly to keep a legacy / short token
CREATE TRIGGER trg_skills_explicit_default
AFTER INSERT ON skills
WHEN NEW.trigger_explicit IS NULL
BEGIN
  UPDATE skills SET trigger_explicit = '--' || NEW.name
  WHERE skill_id = NEW.skill_id;
END;
