-- 061_user_auth_spine.sql — multi-tenant auth spine (app / relational half).
--
-- Pairs with the broker IdP (auth_users in the broker's secrets.db). The two
-- DBs relate by the immutable account_id + the live session token — a handoff,
-- NOT a cross-DB foreign key (decision: broker-as-IdP). Reversible secrets
-- (password, TOTP seed) live ONLY in the broker; this side holds relational
-- identity, sessions, and the audit log.
--
-- No transaction control here — migrate.py wraps the file in one transaction.

-- ── users: relational identity ───────────────────────────────────────────────
-- account_id mirrors the broker's auth_users.account_id (set at create/bootstrap,
-- never here — it must match the broker row). is_admin is user-level (distinct
-- from shells.is_admin). totp_enrolled_at is a non-secret convenience mirror of
-- the broker's enrollment state; the broker remains authoritative.
ALTER TABLE users ADD COLUMN account_id       TEXT;
ALTER TABLE users ADD COLUMN is_admin         INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN totp_enrolled_at TEXT;

-- Backfill the operator (user 1 = the first admin). Email is the login key;
-- set it if blank so the unique index below has a value to anchor.
UPDATE users SET is_admin = 1 WHERE user_id = 1;
UPDATE users SET email = 'jedbjorn@gmail.com'
  WHERE user_id = 1 AND (email IS NULL OR email = '');

-- Email is the login identifier; account_id is the durable cross-DB key. Both
-- unique, enforced by partial indexes (NULLs allowed for not-yet-provisioned
-- rows; a row gets its account_id when its broker auth_user is created).
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email
  ON users(email COLLATE NOCASE) WHERE email IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_account
  ON users(account_id) WHERE account_id IS NOT NULL;

-- ── sessions: server-side, hashed token → user. Hot-path lookup, instant revoke ─
-- token_hash = SHA-256(raw cookie token), hex. The raw token never touches the
-- DB. account_id is denormalized so egress secret calls to the broker need no
-- users join. Sliding 30-day expiry; renewal throttled in the app layer.
CREATE TABLE IF NOT EXISTS sessions (
    token_hash   TEXT    PRIMARY KEY,
    user_id      INTEGER NOT NULL,
    account_id   TEXT,
    ua_hash      TEXT,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    last_seen_at TEXT    NOT NULL DEFAULT (datetime('now')),
    expires_at   TEXT    NOT NULL,
    revoked      INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

-- ── auth_events: append-only audit. Secrets are never logged ──────────────────
CREATE TABLE IF NOT EXISTS auth_events (
    event_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER,
    account_id TEXT,
    email      TEXT,
    kind       TEXT NOT NULL,   -- login_ok | login_fail | totp_fail | session_create
                                -- | session_revoke | user_create | admin_reset | admin_toggle
    detail     TEXT,
    ip         TEXT,            -- CF-Connecting-IP, audit only (no session binding)
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_auth_events_user ON auth_events(user_id);
