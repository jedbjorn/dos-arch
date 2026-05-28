-- 049 — scope the create_flag and resolve_flag tools to their owning skills.
--
-- Audit (CC session 0088) found tools.create_flag (handler=flag.create) and
-- tools.resolve_flag (handler=flag.resolve) carrying skill_id=NULL, so
-- services/dispatch_live.py load_tools() treated them as universal and
-- loaded them for every shell — including Forge, which only owns the
-- create_shell skill. Violates Decision #135 (skills/tools layer split:
-- a purpose-built tool should ride with its skill, not appear globally).
--
-- Root cause: assets/tools/_seed.toml [skill_map] only supported handler-
-- family prefixes (file.*, git.*), one skill per prefix. flag.* needed to
-- split across two skills (create_flag, resolve_flag) and the scheme had
-- no way to express it. This PR extends seed_tools() to accept exact
-- handler entries ("flag.create" → create_flag skill, "flag.resolve" →
-- resolve_flag skill); fresh installs pick the scoping up there. This
-- migration bridges already-bootstrapped substrates.
--
-- Plain SQL: migrate.py owns the transaction and the schema_migrations row.

UPDATE tools
   SET skill_id = (SELECT skill_id FROM skills WHERE name='create_flag' AND is_deleted=0)
 WHERE handler='flag.create'
   AND skill_id IS NULL;

UPDATE tools
   SET skill_id = (SELECT skill_id FROM skills WHERE name='resolve_flag' AND is_deleted=0)
 WHERE handler='flag.resolve'
   AND skill_id IS NULL;
