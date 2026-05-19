-- Rename the local-install inventory table: models -> installed_models.
--
-- CC-48 (M0). PR #19 (migration 015) took the name `models` for the per-host
-- Ollama install inventory. The agnostic-runtime registry (agnostic-runtime
-- §4.1) — every model the system *can* use, with provider / cost / tool
-- dialect — needs that name. This migration frees it: the inventory is
-- renamed, not changed. CC-50 (A1) creates the new `models` registry.
--
-- The PK `model_id` -> `install_id` so it never collides with the registry's
-- own `model_id`. No code references the inventory PK — the sync scripts key
-- on (hardware_id, name) — so the rename touches model_sync.py SQL only.

ALTER TABLE models RENAME TO installed_models;
ALTER TABLE installed_models RENAME COLUMN model_id TO install_id;

DROP INDEX IF EXISTS idx_models_hardware;
CREATE INDEX IF NOT EXISTS idx_installed_models_hardware
    ON installed_models (hardware_id);
