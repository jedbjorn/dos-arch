-- 037 — seed the shared skill + shared tool (host↔container handoff folder).
--
-- The shared folder has existed on disk since the substrate's first install
-- (shared_dirs.ensure_shared_dirs, called from bootstrap + run.py) and is
-- bind-mounted into every shell container at /root/shared. Until now no
-- skill/tool surfaced it — shells didn't know it was there. This migration
-- closes that gap:
--
--   1. INSERTs the `shared` skill (assets/skills/shared.md mirror).
--   2. INSERTs the `shared` tool (assets/tools/shared.md mirror), scoped
--      to the skill via skill_id.
--   3. Grants the skill to every existing browser_chat=1 shell.
--
-- Fresh installs pick the skill + tool up via seed_from_assets at bootstrap
-- (`_seed.toml [skill_map]` carries `shared = "shared"`); this migration
-- only matters for substrates installed before this PR.
--
-- The catalog_universal.md template change adds a `shared` row to the
-- DEFINITIONS table — read live by run.py / boot_document each render, so
-- no DB migration is needed for that.
--
-- INSERT OR IGNORE keeps re-runs idempotent. Plain SQL: migrate.py owns
-- the transaction + the schema_migrations row.

INSERT OR IGNORE INTO skills (name, description, file_path, category, content, command, common) VALUES (
  'shared',
  'Surface this shell''s shared host↔container handoff folder — path + contents.',
  'shell_core/assets/skills/shared.md',
  'workflow',
  '# shared

> **Anchors** — `<self>` = your `shell_id:` value, shown in `## BOOT ##` of
> your CLAUDE.md. `<shortname>` is from `## IDENTITY ##`.

Surface this shell''s shared workspace. Run on demand with `--shared`.

The shared folder is the host↔container handoff surface — see the `shared`
row in `## DEFINITIONS ##`. *Your* subdir is `~/shared/<NN>-<shortname>/`
inside your container, where `NN` is `<self>` zero-padded to two digits
(e.g. `shell_id=2`, `shortname=sysadmin` → `~/shared/02-sysadmin/`).

## Steps

1. **Compute the path** — `~/shared/{<self>:02d}-<shortname>/`. Both
   anchors come straight out of your boot prompt; no lookup needed.
2. **Inspect** — call the `shared` tool with `{"shell_id": <self>,
   "shortname": "<shortname>"}`. Returns the absolute path plus a
   one-level listing of the four subdirs (count + most-recent entry per
   subdir).
   - If you have no `shared` tool (Claude Code CLI surface), use Bash:
     `ls -la ~/shared/<NN>-<shortname>/` then `ls -la` each subdir.
3. **Surface** to FnB — the path on one line, then per-subdir:
   `redlines (3): latest 2026-05-20 mockup.png` etc. If a subdir is
   empty, say so. If the whole tree is empty, state "shared is empty."

## When to use

- FnB says "in shared" / "check shared" / "drop X in shared" — your
  subdir is the target.
- You want to hand a draft / output back to FnB — write it under
  `review/`.
- Cross-shell handoff — the sibling subdirs are visible too (the whole
  host shared root is mounted, not just yours); reach into
  `~/shared/<other-NN>-<other-shortname>/` directly when collaborating.

## When NOT to use

- For source-of-truth memory (seed, L&S, decisions, flags) — those live
  in the DB over the API (see `## MEMORY PROTOCOL ##`). `shared` is
  for files: screenshots, drafts, exports, snapshots.
- For your working repo — that is `/workspace`, separately mounted.
',
  '--shared',
  1
);

INSERT OR IGNORE INTO tools (name, description, kind, spec, handler) VALUES (
  'shared',
  'Inspect this shell''s shared host↔container handoff folder. Returns JSON {path, subdirs: {redlines: {count, latest}, review: {...}, repos: {...}, backups: {...}}}.',
  'builtin',
  '{"type": "object", "properties": {"shell_id": {"type": "integer", "description": "Your shell_id, from ## BOOT ## in your CLAUDE.md."}, "shortname": {"type": "string", "description": "Your shortname, from ## IDENTITY ## in your CLAUDE.md."}}, "required": ["shell_id", "shortname"]}',
  'shared.inspect'
);

-- Scope the tool to the skill (mirrors what seed_tools does for fresh installs
-- via the _seed.toml [skill_map]).
UPDATE tools
   SET skill_id = (SELECT skill_id FROM skills WHERE name='shared' AND is_deleted=0)
 WHERE handler LIKE 'shared.%' AND skill_id IS NULL;

-- Grant the skill to every browser_chat=1 shell (sysadmin today; future
-- browser-chat shells get it via the common=1 grant path at creation).
INSERT OR IGNORE INTO shell_skills (shell_id, skill_id)
SELECT s.shell_id, sk.skill_id
  FROM shells s, skills sk
 WHERE s.browser_chat = 1
   AND sk.name = 'shared'
   AND sk.is_deleted = 0;
