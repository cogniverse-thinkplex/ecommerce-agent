CREATE TABLE policy_documents (
    policy_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    summary TEXT NOT NULL,
    source_url TEXT NOT NULL,
    scope TEXT NOT NULL,
    official_version TEXT,
    verified_at TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE policy_chunks (
    chunk_id TEXT PRIMARY KEY,
    policy_id TEXT NOT NULL REFERENCES policy_documents(policy_id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    content TEXT NOT NULL,
    token_text TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    embedding BLOB,
    embedding_model TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(policy_id, sequence)
);

CREATE VIRTUAL TABLE policy_chunks_fts USING fts5(
    chunk_id UNINDEXED,
    policy_id UNINDEXED,
    token_text
);

CREATE TABLE policy_ingestion_runs (
    run_id TEXT PRIMARY KEY,
    corpus_version TEXT NOT NULL,
    embedding_model TEXT,
    document_count INTEGER NOT NULL,
    chunk_count INTEGER NOT NULL,
    status TEXT NOT NULL,
    error_summary TEXT,
    created_at TEXT NOT NULL
);
