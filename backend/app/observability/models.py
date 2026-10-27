from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field, field_validator


class FeedbackCreate(BaseModel):
    message_id: str | None = None
    rating: Literal["helpful", "not_helpful"]
    category: Literal["resolved", "incorrect", "unclear", "slow", "tool_failure", "other"] | None = None
    comment: str | None = Field(default=None, max_length=2000)


class IssueFeedbackCreate(BaseModel):
    conversation_id: str | None = None
    category: Literal["incorrect", "unclear", "slow", "tool_failure", "interface", "other"]
    comment: str = Field(min_length=1, max_length=2000)

    @field_validator("comment")
    @classmethod
    def comment_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("feedback description cannot be blank")
        return value


class FeedbackPublic(BaseModel):
    feedback_id: str
    conversation_id: str | None
    message_id: str | None
    rating: str
    category: str | None
    comment: str | None
    status: str
    created_at: str
    updated_at: str


class FeedbackReview(BaseModel):
    status: Literal["new", "reviewing", "resolved", "dismissed"]
    developer_note: str | None = Field(default=None, max_length=4000)


class IssueReview(BaseModel):
    status: Literal["open", "investigating", "resolved", "resolved_verified", "ignored"]
    developer_note: str | None = Field(default=None, max_length=4000)


class FeedbackPage(BaseModel):
    items: list[dict]
    total: int


class IssuePage(BaseModel):
    items: list[dict]
    total: int


class ObservabilityOverview(BaseModel):
    health: str = "ok"
    issues_24h: int = 0
    open_critical_issues: int = 0
    new_feedback: int = 0
    negative_feedback: int = 0
    latest_evaluation_success_rate: float | None = None
    evaluation_status: str = "unavailable"
