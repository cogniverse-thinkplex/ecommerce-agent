CREATE TABLE conversation_groups (
    group_id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL REFERENCES users(user_id),
    name TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (owner_user_id, name)
);

ALTER TABLE conversations ADD COLUMN group_id TEXT REFERENCES conversation_groups(group_id) ON DELETE SET NULL;
ALTER TABLE conversations ADD COLUMN is_pinned INTEGER NOT NULL DEFAULT 0 CHECK (is_pinned IN (0, 1));
ALTER TABLE conversations ADD COLUMN title_source TEXT NOT NULL DEFAULT 'auto' CHECK (title_source IN ('auto', 'custom'));

CREATE INDEX idx_conversation_groups_owner_sort ON conversation_groups(owner_user_id, sort_order, created_at);
CREATE INDEX idx_conversations_owner_group_pinned ON conversations(owner_user_id, group_id, is_pinned, updated_at);

