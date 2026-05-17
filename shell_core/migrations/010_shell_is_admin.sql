-- Admin flag on shells. is_admin=1 grants a shell's substrate-API key the
-- admin scope (POST /admin/shells, skill CRUD, …) — see api/common/auth.py.
-- Only Sys-Admin is an admin shell; worker shells stay is_admin=0.
-- On a live substrate the column lands at 0 for everyone, so backfill the
-- existing Sys-Admin row.
ALTER TABLE shells ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0;
UPDATE shells SET is_admin = 1 WHERE shortname = 'sysadmin';
