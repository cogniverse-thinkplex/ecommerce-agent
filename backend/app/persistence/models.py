from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agent.state import CustomerAgentState


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ConversationRecord(BaseModel):
    conversation_id: str
    title: str = "新会话"
    status: Literal["active", "archived"] = "active"
    owner_user_id: str | None = None
    group_id: str | None = None
    is_pinned: bool = False
    title_source: Literal["auto", "custom"] = "auto"
    authenticated_user_id: str | None = None
    authentication_method: Literal["email", "name_zip"] | None = None
    state: CustomerAgentState
    last_error_code: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ConversationGroupRecord(BaseModel):
    group_id: str
    owner_user_id: str
    name: str = Field(min_length=1, max_length=80)
    sort_order: int = 0
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class MessageRecord(BaseModel):
    message_id: str
    conversation_id: str
    sequence: int = Field(ge=1)
    role: Literal["user", "assistant", "system", "action"]
    kind: str
    text: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    delivery_state: Literal["pending", "delivered", "failed"] = "delivered"
    request_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


ActionStatus = Literal[
    "pending", "confirmed", "rejected", "executing", "succeeded", "failed"
]


class PendingActionRecord(BaseModel):
    action_id: str
    conversation_id: str
    tool_name: str
    arguments: dict[str, Any]
    fingerprint: str
    idempotency_key: str
    confirmation_summary: str
    status: ActionStatus = "pending"
    result: dict[str, Any] | None = None
    failure_code: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    resolved_at: datetime | None = None


HandoffStatus = Literal["open", "in_progress", "resolved", "cancelled"]


class HumanHandoffRecord(BaseModel):
    ticket_id: str
    conversation_id: str
    owner_user_id: str
    reason: str
    customer_message: str | None = None
    context_summary: str = ""
    status: HandoffStatus = "open"
    assigned_developer_user_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    resolved_at: datetime | None = None


class AuditEventRecord(BaseModel):
    event_id: str
    conversation_id: str
    action_id: str | None = None
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class UserRecord(BaseModel):
    user_id: str
    email: str
    display_name: str
    password_hash: str
    role: Literal["customer", "developer"]
    status: Literal["active", "disabled"] = "active"
    must_change_password: bool = False
    retail_user_id: str | None = None
    created_by_user_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    last_login_at: datetime | None = None


class CustomerAddressRecord(BaseModel):
    address_id: str
    owner_user_id: str
    recipient_name: str
    phone: str = ""
    address1: str
    address2: str = ""
    city: str
    state: str
    country: str
    zip: str
    is_default: bool = False
    status: Literal["active", "archived"] = "active"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class DemoOrderMetadataRecord(BaseModel):
    order_id: str
    purchased_at: datetime
    created_at: datetime = Field(default_factory=utc_now)


class PolicyDocumentRecord(BaseModel):
    policy_id: str
    title: str
    category: str
    summary: str
    source_url: str
    scope: str
    official_version: str | None = None
    verified_at: str
    content_hash: str
    enabled: bool = True
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class PolicyChunkRecord(BaseModel):
    chunk_id: str
    policy_id: str
    sequence: int
    content: str
    token_text: str
    content_hash: str
    embedding: bytes | None = None
    embedding_model: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class AuthSessionRecord(BaseModel):
    session_id: str
    user_id: str
    token_hash: str
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime
    last_seen_at: datetime = Field(default_factory=utc_now)
    revoked_at: datetime | None = None


class AuthAuditEventRecord(BaseModel):
    event_id: str
    user_id: str | None = None
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class FeedbackRecord(BaseModel):
    feedback_id: str
    user_id: str
    conversation_id: str | None = None
    message_id: str | None = None
    rating: Literal["helpful", "not_helpful"]
    category: Literal["resolved", "incorrect", "unclear", "slow", "tool_failure", "interface", "other"] | None = None
    comment: str | None = Field(default=None, max_length=2000)
    status: Literal["new", "reviewing", "resolved", "dismissed"] = "new"
    developer_note: str | None = Field(default=None, max_length=4000)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    resolved_by_user_id: str | None = None


class RuntimeIssueRecord(BaseModel):
    issue_id: str
    fingerprint: str
    source: Literal["api", "planner", "tool", "mcp", "database", "frontend"]
    severity: Literal["warning", "error", "critical"]
    error_code: str
    summary: str
    sanitized_detail: str | None = None
    status: Literal[
        "open", "investigating", "resolved", "resolved_verified", "ignored"
    ] = "open"
    occurrence_count: int = Field(default=1, ge=1)
    first_seen_at: datetime = Field(default_factory=utc_now)
    last_seen_at: datetime = Field(default_factory=utc_now)
    last_request_id: str | None = None
    last_conversation_id: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    developer_note: str | None = Field(default=None, max_length=4000)
    resolved_by_user_id: str | None = None
    resolved_at: datetime | None = None


class AgentRunRecord(BaseModel):
    run_id: str
    conversation_id: str | None = None
    source: Literal["support", "sandbox", "benchmark", "regression"]
    planner_type: Literal["rule", "llm"]
    model: str | None = None
    tool_backend: str
    policy_version: str | None = None
    data_version: str | None = None
    status: Literal[
        "running", "succeeded", "failed", "waiting_confirmation", "cancelled"
    ]
    stopped_reason: str | None = None
    business_success: bool | None = None
    confirmation_gate_success: bool | None = None
    confirmed_outcome_success: bool | None = None
    exact_match: bool | None = None
    step_count: int = Field(default=0, ge=0)
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    estimated_cost_cny: float | None = Field(default=None, ge=0)
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    error_code: str | None = None
    issue_id: str | None = None


class AgentRunStepRecord(BaseModel):
    step_id: str
    run_id: str
    sequence: int = Field(default=0, ge=0)
    kind: Literal["planner", "tool", "guard", "confirmation", "response"]
    name: str
    status: Literal["running", "succeeded", "failed", "blocked"]
    duration_ms: int | None = Field(default=None, ge=0)
    summary: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None


class RegressionCaseRecord(BaseModel):
    case_id: str
    name: str
    description: str = ""
    origin_type: Literal["tau2", "issue", "feedback", "conversation", "manual"]
    origin_id: str | None = None
    fixture_type: Literal["tau2_task", "conversation_replay"]
    fixture: dict[str, Any] = Field(default_factory=dict)
    expected: dict[str, Any] = Field(default_factory=dict)
    status: Literal["draft", "active", "retired"] = "draft"
    created_by_user_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class RegressionCaseRunRecord(BaseModel):
    case_run_id: str
    case_id: str
    agent_run_id: str | None = None
    batch_id: str
    status: Literal["queued", "running", "passed", "failed", "blocked"]
    failure_reason: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None

