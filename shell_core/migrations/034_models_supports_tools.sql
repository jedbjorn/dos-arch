-- 034 — record per-model tool-call capability and filter no-tool models.
--
-- Ollama's installed set contains models whose templates do not declare the
-- `tools` capability (e.g. phi3:mini). The dispatcher always sends a tools
-- array — Ollama then 400s the call ("does not support tools") and the
-- dispatcher swallows the error as a generic "overloaded" reply. dos-arch is
-- a tool-driven substrate; a no-tool model can't honor the shell contract.
--
-- Decision: filter no-tool models out of the picker. Cloud models are
-- assumed to support tools (every active row we ship does). Local rows have
-- their capability re-derived by `dosarch-modelsync` from Ollama's
-- /api/show `capabilities`; non-tool rows are kept in the registry as
-- inactive (so we can see what was filtered) but never reach the dropdown.
--
-- This migration:
--   1. adds the column (default 0 — unknown until proven),
--   2. marks cloud rows supports_tools=1,
--   3. flips already-active local rows whose capability we cannot yet read
--      to inactive — dosarch-modelsync's first watch tick after deploy
--      restores any that do support tools, and leaves the rest off.

ALTER TABLE models ADD COLUMN supports_tools INTEGER NOT NULL DEFAULT 0;

UPDATE models
   SET supports_tools = 1
 WHERE provider IN ('anthropic','openai','google');

-- Local rows: mark unknown and pull them out of the picker. Modelsync's
-- next sync will re-evaluate every installed model against /api/show and
-- promote the tool-capable ones back to active with supports_tools=1.
UPDATE models
   SET supports_tools = 0,
       status = 'inactive'
 WHERE provider = 'local';
