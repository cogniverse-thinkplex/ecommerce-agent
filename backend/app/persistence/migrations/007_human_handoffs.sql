CREATE TABLE human_handoffs (
    ticket_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    owner_user_id TEXT NOT NULL REFERENCES users(user_id),
    reason TEXT NOT NULL,
    customer_message TEXT,
    context_summary TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'in_progress', 'resolved', 'cancelled')),
    assigned_developer_user_id TEXT REFERENCES users(user_id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE INDEX idx_handoffs_status_updated ON human_handoffs(status, updated_at DESC);
CREATE INDEX idx_handoffs_conversation_status ON human_handoffs(conversation_id, status);
CREATE INDEX idx_handoffs_owner_updated ON human_handoffs(owner_user_id, updated_at DESC);
CREATE UNIQUE INDEX idx_handoffs_one_active_conversation
ON human_handoffs(conversation_id)
WHERE status IN ('open', 'in_progress');
