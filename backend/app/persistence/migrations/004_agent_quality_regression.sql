PRAGMA foreign_keys=OFF;

CREATE TABLE runtime_issues_v4 (
    issue_id TEXT PRIMARY KEY,
    fingerprint TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL CHECK (source IN ('api', 'planner', 'tool', 'mcp', 'database', 'frontend')),
    severity TEXT NOT NULL CHECK (severity IN ('warning', 'error', 'critical')),
    error_code TEXT NOT NULL,
    summary TEXT NOT NULL,
    sanitized_detail TEXT,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'investigating', 'resolved', 'resolved_verified', 'ignored')),
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

INSERT INTO runtime_issues_v4 SELECT * FROM runtime_issues;
DROP TABLE runtime_issues;
ALTER TABLE runtime_issues_v4 RENAME TO runtime_issues;
CREATE INDEX idx_issues_status_severity_seen ON runtime_issues(status, severity, last_seen_at);
CREATE INDEX idx_issues_source_code ON runtime_issues(source, error_code);
CREATE INDEX idx_issues_conversation_seen ON runtime_issues(last_conversation_id, last_seen_at);

CREATE TABLE agent_runs (
    run_id TEXT PRIMARY KEY,
    conversation_id TEXT,
    source TEXT NOT NULL CHECK (source IN ('support', 'sandbox', 'benchmark', 'regression')),
    planner_type TEXT NOT NULL CHECK (planner_type IN ('rule', 'llm')),
    model TEXT,
    tool_backend TEXT NOT NULL,
    policy_version TEXT,
    data_version TEXT,
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed', 'waiting_confirmation', 'cancelled')),
    stopped_reason TEXT,
    business_success INTEGER,
    confirmation_gate_success INTEGER,
    confirmed_outcome_success INTEGER,
    exact_match INTEGER,
    step_count INTEGER NOT NULL DEFAULT 0 CHECK (step_count >= 0),
    prompt_tokens INTEGER CHECK (prompt_tokens IS NULL OR prompt_tokens >= 0),
    completion_tokens INTEGER CHECK (completion_tokens IS NULL OR completion_tokens >= 0),
    total_tokens INTEGER CHECK (total_tokens IS NULL OR total_tokens >= 0),
    estimated_cost_cny REAL CHECK (estimated_cost_cny IS NULL OR estimated_cost_cny >= 0),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    duration_ms INTEGER CHECK (duration_ms IS NULL OR duration_ms >= 0),
    error_code TEXT,
    issue_id TEXT,
    FOREIGN KEY(conversation_id) REFERENCES conversations(conversation_id) ON DELETE SET NULL,
    FOREIGN KEY(issue_id) REFERENCES runtime_issues(issue_id) ON DELETE SET NULL
);
CREATE INDEX idx_agent_runs_started ON agent_runs(started_at DESC);
CREATE INDEX idx_agent_runs_status_started ON agent_runs(status, started_at DESC);
CREATE INDEX idx_agent_runs_source_planner ON agent_runs(source, planner_type, started_at DESC);
CREATE INDEX idx_agent_runs_conversation ON agent_runs(conversation_id, started_at DESC);

CREATE TABLE agent_run_steps (
    step_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence >= 1),
    kind TEXT NOT NULL CHECK (kind IN ('planner', 'tool', 'guard', 'confirmation', 'response')),
    name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed', 'blocked')),
    duration_ms INTEGER CHECK (duration_ms IS NULL OR duration_ms >= 0),
    summary_json TEXT NOT NULL DEFAULT '{}',
    started_at TEXT NOT NULL,
    finished_at TEXT,
    FOREIGN KEY(run_id) REFERENCES agent_runs(run_id) ON DELETE CASCADE,
    UNIQUE(run_id, sequence)
);
CREATE INDEX idx_agent_run_steps_run ON agent_run_steps(run_id, sequence);
CREATE INDEX idx_agent_run_steps_kind_status ON agent_run_steps(kind, status, started_at DESC);

CREATE TABLE regression_cases (
    case_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    origin_type TEXT NOT NULL CHECK (origin_type IN ('tau2', 'issue', 'feedback', 'conversation', 'manual')),
    origin_id TEXT,
    fixture_type TEXT NOT NULL CHECK (fixture_type IN ('tau2_task', 'conversation_replay')),
    fixture_json TEXT NOT NULL DEFAULT '{}',
    expected_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'retired')),
    created_by_user_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(created_by_user_id) REFERENCES users(user_id) ON DELETE SET NULL
);
CREATE UNIQUE INDEX idx_regression_cases_origin ON regression_cases(origin_type, origin_id) WHERE origin_id IS NOT NULL;
CREATE INDEX idx_regression_cases_status_updated ON regression_cases(status, updated_at DESC);

CREATE TABLE regression_case_runs (
    case_run_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    agent_run_id TEXT,
    batch_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'passed', 'failed', 'blocked')),
    failure_reason TEXT,
    created_at TEXT NOT NULL,
    finished_at TEXT,
    FOREIGN KEY(case_id) REFERENCES regression_cases(case_id) ON DELETE CASCADE,
    FOREIGN KEY(agent_run_id) REFERENCES agent_runs(run_id) ON DELETE SET NULL
);
CREATE INDEX idx_case_runs_case_created ON regression_case_runs(case_id, created_at DESC);
CREATE INDEX idx_case_runs_batch_created ON regression_case_runs(batch_id, created_at);

PRAGMA foreign_keys=ON;
