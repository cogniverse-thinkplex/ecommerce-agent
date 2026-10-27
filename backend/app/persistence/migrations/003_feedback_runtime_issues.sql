CREATE TABLE user_feedback (
    feedback_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    message_id TEXT,
    rating TEXT NOT NULL CHECK (rating IN ('helpful', 'not_helpful')),
    category TEXT CHECK (category IS NULL OR category IN ('resolved', 'incorrect', 'unclear', 'slow', 'tool_failure', 'other')),
    comment TEXT,
    status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'reviewing', 'resolved', 'dismissed')),
    developer_note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    resolved_by_user_id TEXT,
    FOREIGN KEY(user_id) REFERENCES users(user_id),
    FOREIGN KEY(conversation_id) REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    FOREIGN KEY(message_id) REFERENCES messages(message_id),
    FOREIGN KEY(resolved_by_user_id) REFERENCES users(user_id)
);
CREATE INDEX idx_feedback_conversation_created ON user_feedback(conversation_id, created_at);
CREATE INDEX idx_feedback_status_created ON user_feedback(status, created_at);
CREATE INDEX idx_feedback_rating_category ON user_feedback(rating, category);

CREATE TABLE runtime_issues (
    issue_id TEXT PRIMARY KEY,
    fingerprint TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL CHECK (source IN ('api', 'planner', 'tool', 'mcp', 'database', 'frontend')),
    severity TEXT NOT NULL CHECK (severity IN ('warning', 'error', 'critical')),
    error_code TEXT NOT NULL,
    summary TEXT NOT NULL,
    sanitized_detail TEXT,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'investigating', 'resolved', 'ignored')),
    occurrence_count INTEGER NOT NULL DEFAULT 1 CHECK (occurrence_count >= 1),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    last_request_id TEXT,
    last_conversation_id TEXT,
    context_json TEXT NOT NULL DEFAULT '{}',
    developer_note TEXT,
    resolved_by_user_id TEXT,
    resolved_at TEXT,
    FOREIGN KEY(last_conversation_id) REFERENCES conversations(conversation_id) ON DELETE SET NULL,
    FOREIGN KEY(resolved_by_user_id) REFERENCES users(user_id)
);
CREATE INDEX idx_issues_status_severity_seen ON runtime_issues(status, severity, last_seen_at);
CREATE INDEX idx_issues_source_code ON runtime_issues(source, error_code);
CREATE INDEX idx_issues_conversation_seen ON runtime_issues(last_conversation_id, last_seen_at);
