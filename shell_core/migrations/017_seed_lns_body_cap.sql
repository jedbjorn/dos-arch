-- Per-kind body caps on seed / L&S entries (shell_identity_entries.body).
--
-- seed and L&S are already count-capped (10 / 20, via trg_sie_cap_*). This
-- adds a size cap per entry, and the two kinds differ. An L&S is an
-- imperative craft principle — 400 chars, the memory-recall spec's "index
-- entry" budget. A seed is an identity-forming moment, reflective by
-- nature — given more room, 800 chars. Either way the entry is distilled,
-- not a log.
--
-- BEFORE INSERT only — identity bodies are immutable (Law 3: retire, never
-- edit), so a body is only ever written once. Existing rows are untouched.

CREATE TRIGGER trg_sie_body_cap_seed
BEFORE INSERT ON shell_identity_entries
WHEN NEW.kind = 'seed' AND length(NEW.body) > 800
BEGIN
  SELECT RAISE(ABORT, 'seed entry body exceeds 800 chars — a distilled moment, not a log; trim it');
END;

CREATE TRIGGER trg_sie_body_cap_lns
BEFORE INSERT ON shell_identity_entries
WHEN NEW.kind = 'lns' AND length(NEW.body) > 400
BEGIN
  SELECT RAISE(ABORT, 'L&S entry body exceeds 400 chars — a distilled principle, not a log; trim it');
END;
