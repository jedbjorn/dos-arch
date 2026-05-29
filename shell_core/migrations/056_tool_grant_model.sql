-- 056 — tool grant model: M:N skill_tools + reintroduced shell_tools.
--   tools.is_general (new), skill_tools (new), shell_tools (new), tools.skill_id (dropped)
--
-- Reverses migration 025's "the skill is the unit of granting, no per-shell
-- tool table" premise. Two needs the 1:1 tools.skill_id could not meet:
--   • a tool may be required by more than one skill — now an M:N join
--     (skill_tools), not a single column;
--   • a tool may be granted to a shell directly, independent of any skill —
--     now a per-shell grant table (shell_tools), reintroduced after 025.
--
-- The effective tool set for a shell becomes:
--   general (tools.is_general=1 — every shell, the api_* verbs)
--   ∪ shell_tools (direct grants for that shell).
-- Assigning a skill MATERIALISES its skill_tools into shell_tools (done by the
-- API, not here), so a skill's tools are freely toggleable afterwards. The old
-- "general = skill_id NULL" signal moves to the explicit is_general flag.
--
-- Backfill preserves every shell's current effective grants exactly:
--   • is_general=1 for what was skill_id NULL;
--   • skill_tools mirrors the old 1:1 skill_id;
--   • shell_tools = each shell's assigned skills × their tools (= old render).
-- So no shell gains or loses a tool across this migration.
--
-- Plain SQL: migrate.py owns the transaction and the schema_migrations row.

ALTER TABLE tools ADD COLUMN is_general INTEGER NOT NULL DEFAULT 0;

CREATE TABLE skill_tools (
    skill_tool_id INTEGER PRIMARY KEY,
    skill_id      INTEGER NOT NULL REFERENCES skills(skill_id),
    tool_id       INTEGER NOT NULL REFERENCES tools(tool_id),
    UNIQUE (skill_id, tool_id)
);

CREATE TABLE shell_tools (
    shell_tool_id INTEGER PRIMARY KEY,
    shell_id      INTEGER NOT NULL REFERENCES shells(shell_id),
    tool_id       INTEGER NOT NULL REFERENCES tools(tool_id),
    UNIQUE (shell_id, tool_id)
);

-- Backfill, in order: flag the general tools, mirror the old 1:1 skill scoping
-- into the M:N join, then materialise the per-shell grants from the join.
UPDATE tools SET is_general=1 WHERE skill_id IS NULL;

INSERT INTO skill_tools (skill_id, tool_id)
    SELECT skill_id, tool_id FROM tools WHERE skill_id IS NOT NULL;

INSERT OR IGNORE INTO shell_tools (shell_id, tool_id)
    SELECT ss.shell_id, st.tool_id
    FROM shell_skills ss
    JOIN skill_tools st ON st.skill_id = ss.skill_id;

ALTER TABLE tools DROP COLUMN skill_id;
