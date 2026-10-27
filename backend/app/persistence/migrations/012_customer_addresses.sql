CREATE TABLE customer_addresses (
    address_id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL REFERENCES users(user_id),
    recipient_name TEXT NOT NULL,
    phone TEXT NOT NULL DEFAULT '',
    address1 TEXT NOT NULL,
    address2 TEXT NOT NULL DEFAULT '',
    city TEXT NOT NULL,
    state TEXT NOT NULL,
    country TEXT NOT NULL,
    zip TEXT NOT NULL,
    is_default INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_customer_addresses_owner ON customer_addresses(owner_user_id, status, updated_at);
CREATE UNIQUE INDEX idx_customer_addresses_one_default ON customer_addresses(owner_user_id)
WHERE is_default = 1 AND status = 'active';
