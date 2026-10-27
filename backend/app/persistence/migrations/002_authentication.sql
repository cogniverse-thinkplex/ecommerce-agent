CREATE TABLE users (
    user_id TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('customer', 'developer')),
    status TEXT NOT NULL CHECK (status IN ('active', 'disabled')) DEFAULT 'active',
    must_change_password INTEGER NOT NULL CHECK (must_change_password IN (0, 1)) DEFAULT 0,
    created_by_user_id TEXT REFERENCES users(user_id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_login_at TEXT
);

CREATE UNIQUE INDEX idx_users_email_normalized ON users(lower(trim(email)));
CREATE INDEX idx_users_role_status ON users(role, status);

CREATE TABLE auth_sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    revoked_at TEXT
);

CREATE INDEX idx_auth_sessions_user ON auth_sessions(user_id, expires_at);

CREATE TABLE auth_audit_events (
    event_id TEXT PRIMARY KEY,
    user_id TEXT REFERENCES users(user_id),
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_auth_audit_user_created ON auth_audit_events(user_id, created_at);

ALTER TABLE conversations ADD COLUMN owner_user_id TEXT REFERENCES users(user_id);
CREATE INDEX idx_conversations_owner_updated ON conversations(owner_user_id, updated_at);

INSERT INTO users (
    user_id, email, display_name, password_hash, role, status,
    must_change_password, created_by_user_id, created_at, updated_at
) VALUES (
    '00000000-0000-0000-0000-000000000001',
    'admin@local.dev',
    '初始管理员',
    'scrypt$v=1$n=16384$r=8$p=1$bG9jYWwtYWRtaW4tdjE$WbDbuXjQU7R_Qr4iNTt3zNoAP8k3JJO5HCnxqcH_O6k',
    'developer',
    'active',
    1,
    NULL,
    '2026-10-21T00:00:00+00:00',
    '2026-10-21T00:00:00+00:00'
);
