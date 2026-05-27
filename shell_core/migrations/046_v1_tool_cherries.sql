-- 046 — v1 tool cherries: file_copy, file_mkdir, file_apply_patch.
--
-- First port from the external coding-agent catalogue scan (CC-092 in
-- superCC). file_copy + file_mkdir close obvious holes in the file_*
-- family (picocode primitives we lacked). file_apply_patch is the
-- multi-hunk atomic-edit primitive borrowed from OpenCode's apply_patch
-- — adapted to dos-arch's typed spec instead of OpenCode's embedded-
-- path-marker patch text. Hunks are (path, old_str, new_str) triples
-- with the same uniqueness rule as file_edit; pre-flight resolves every
-- hunk in memory before any file is written, so a single failure aborts
-- the batch cleanly.
--
-- INSERT OR IGNORE: fresh installs already pick these up via
-- seed_from_assets reading assets/tools/*.md at bootstrap; this
-- migration matters for already-bootstrapped substrates.
--
-- The trailing UPDATE re-scopes any new file.* tools onto the file-ops
-- skill (handler-prefix convention from migration 026 / _seed.toml).
-- For fresh installs this is a no-op — seed_tools already did it.
--
-- Plain SQL: migrate.py owns the transaction and the schema_migrations row.

INSERT OR IGNORE INTO tools (name, description, kind, spec, handler) VALUES (
  'file_copy',
  'Copy a file to a new path. Refuses if the destination already exists.',
  'builtin',
  '{"type": "object", "properties": {"src": {"type": "string", "description": "source path"}, "dst": {"type": "string", "description": "destination path"}}, "required": ["src", "dst"]}',
  'file.copy'
);

INSERT OR IGNORE INTO tools (name, description, kind, spec, handler) VALUES (
  'file_mkdir',
  'Create a directory. Parents are created as needed; succeeds silently if the directory already exists.',
  'builtin',
  '{"type": "object", "properties": {"path": {"type": "string", "description": "directory path to create"}}, "required": ["path"]}',
  'file.mkdir'
);

INSERT OR IGNORE INTO tools (name, description, kind, spec, handler) VALUES (
  'file_apply_patch',
  'Apply a batch of structured edits across one or more files atomically — all hunks succeed or none are written. Each hunk is a (path, old_str, new_str) triple with the same uniqueness rule as file_edit.',
  'builtin',
  '{"type": "object", "properties": {"hunks": {"type": "array", "description": "ordered list of edits to apply atomically", "items": {"type": "object", "properties": {"path": {"type": "string", "description": "file path to edit"}, "old_str": {"type": "string", "description": "exact substring to replace; must match uniquely in the file"}, "new_str": {"type": "string", "description": "replacement substring"}}, "required": ["path", "old_str", "new_str"]}, "minItems": 1}}, "required": ["hunks"]}',
  'file.apply_patch'
);

UPDATE tools SET skill_id = (SELECT skill_id FROM skills WHERE name='file-ops')
  WHERE handler LIKE 'file.%' AND skill_id IS NULL;
