-- 036 — tools.prompt_block: each tool owns its rendered TOOLS-section block.
--
-- Before: render_tools() emitted a flat name + description roster, dialect-
-- branched, with one shared invocation example for the parsed dialect. Small
-- models could not form a real call from that — name + a one-line description
-- is not enough; they need when-to-use, the input shape, and a worked example
-- per tool.
--
-- After: each tool's prompt_block carries that per-tool section, authored in
-- assets/tools/<name>.md under the <!-- @@ PROMPT @@ --> marker (sibling of
-- the SPEC marker that carries the JSON Schema). render_tools concatenates
-- the blocks. catalog_universal.md no longer carries the strings.
--
-- parsed_example (migration 020) was never read by code and is subsumed by
-- prompt_block — drop it. SQLite 3.35+ supports DROP COLUMN; the substrate
-- already requires 3.35+ via WAL + JSON1 patterns elsewhere.
--
-- Plain SQL: migrate.py owns the transaction and the schema_migrations row.

ALTER TABLE tools ADD COLUMN prompt_block TEXT;
ALTER TABLE tools DROP COLUMN parsed_example;
