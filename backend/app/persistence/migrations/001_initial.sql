CREATE TABLE IF NOT EXISTS conversations (
    conversation_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'archived')),
    authenticated_user_id TEXT,
    authentication_method TEXT,
    state_json TEXT NOT NULL,
    last_error_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    message_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id),
    sequence INTEGER NOT NULL CHECK (sequence > 0),
    role TEXT NOT NULL,
    kind TEXT NOT NULL,
    text TEXT,
    payload_json TEXT NOT NULL,
    delivery_state TEXT NOT NULL,
    request_id TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (conversation_id, sequence),
    UNIQUE (conversation_id, request_id)
);

CREATE TABLE IF NOT EXISTS pending_actions (
    action_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id),
    tool_name TEXT NOT NULL,
    arguments_json TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    confirmation_summary TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('pending', 'confirmed', 'rejected', 'executing', 'succeeded', 'failed')
    ),
    result_json TEXT,
    failure_code TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id),
    action_id TEXT REFERENCES pending_actions(action_id),
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_sequence
    ON messages(conversation_id, sequence);
CREATE INDEX IF NOT EXISTS idx_actions_conversation_created
    ON pending_actions(conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_conversation_created
    ON audit_events(conversation_id, created_at);

