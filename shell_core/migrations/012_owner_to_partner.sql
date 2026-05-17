-- Rename shells.owner → shells.partner. The operator relates to a shell as
-- a partner, not an owner — "owner" framing was pervasive across the field,
-- the FnB definition, and the bootstrap docs (Sys-Admin E2E gap 14, flag
-- SYSADMIN-001). This is the schema half; the code + docs are renamed in
-- the same change. The free-text human-name string only — shells.user_id
-- (the owning-user FK) is a separate concept and is untouched.
ALTER TABLE shells RENAME COLUMN owner TO partner;
