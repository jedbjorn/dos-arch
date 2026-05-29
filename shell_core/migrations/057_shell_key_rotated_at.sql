-- 057 — shell API-key rotation metadata: shells.api_key_rotated_at (new).
--
-- CC-102 Phase 2 (reframed). The vault migration the flag originally planned
-- was dropped: the broker exposes no plaintext-read route by design and its
-- store lives in a container-only volume the host dispatcher cannot reach,
-- while a shell key only unlocks the loopback-bound substrate API (low value).
-- So shell keys stay in the DB (api_key plaintext + api_key_hash) and Phase 2
-- narrows to operational polish: a working manual rotate + this timestamp.
--
-- api_key_rotated_at records when the current key was last established (minted
-- or rotated). Written by ensure_api_keys.ensure_keys / rotate_key and by the
-- admin rotate endpoint; surfaced per-shell in the Keys UI. NULL only for a
-- shell that has never been keyed.
--
-- ALTER ADD COLUMN cannot take a non-constant default, so the column lands
-- NULL and existing keyed shells are backfilled to now as their baseline.
--
-- Plain SQL: migrate.py owns the transaction and the schema_migrations row.

ALTER TABLE shells ADD COLUMN api_key_rotated_at TEXT;

UPDATE shells
   SET api_key_rotated_at = datetime('now')
 WHERE api_key_hash IS NOT NULL
   AND api_key_rotated_at IS NULL;
