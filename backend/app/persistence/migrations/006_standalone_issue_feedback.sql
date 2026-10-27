CREATE TABLE user_feedback_next (
    feedback_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    conversation_id TEXT,
    message_id TEXT,
    rating TEXT NOT NULL CHECK (rating IN ('helpful', 'not_helpful')),
    category TEXT CHECK (category IS NULL OR category IN ('resolved', 'incorrect', 'unclear', 'slow', 'tool_failure', 'interface', 'other')),
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

INSERT INTO user_feedback_next (
    feedback_id, user_id, conversation_id, message_id, rating, category, comment,
    status, developer_note, created_at, updated_at, resolved_by_user_id
)
SELECT
    feedback_id, user_id, conversation_id, message_id, rating, category, comment,
    status, developer_note, created_at, updated_at, resolved_by_user_id
FROM user_feedback;

DROP TABLE user_feedback;
ALTER TABLE user_feedback_next RENAME TO user_feedback;

CREATE INDEX idx_feedback_conversation_created ON user_feedback(conversation_id, created_at);
CREATE INDEX idx_feedback_status_created ON user_feedback(status, created_at);
CREATE INDEX idx_feedback_rating_category ON user_feedback(rating, category);
