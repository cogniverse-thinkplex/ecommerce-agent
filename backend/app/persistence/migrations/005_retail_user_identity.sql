ALTER TABLE users ADD COLUMN retail_user_id TEXT;
CREATE UNIQUE INDEX idx_users_retail_user_id
    ON users(retail_user_id) WHERE retail_user_id IS NOT NULL;
