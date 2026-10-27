from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class StartRunCommand(BaseModel):
    conversation_id: str | None = None
    source: Literal["support", "sandbox", "benchmark", "regression"]
    planner_type: Literal["rule", "llm"]
    model: str | None = None
    tool_backend: str
    policy_version: str | None = None
    data_version: str | None = None
    started_at: datetime | None = None


class RecordStepCommand(BaseModel):
    kind: Literal["planner", "tool", "guard", "confirmation", "response"]
    name: str
    status: Literal["running", "succeeded", "failed", "blocked"]
    summary: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)


class FinishRunCommand(BaseModel):
    status: Literal["succeeded", "failed", "waiting_confirmation", "cancelled"]
    stopped_reason: str | None = None
    business_success: bool | None = None
    confirmation_gate_success: bool | None = None
    confirmed_outcome_success: bool | None = None
    exact_match: bool | None = None
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    estimated_cost_cny: float | None = Field(default=None, ge=0)
    finished_at: datetime | None = None
    error_code: str | None = None
    issue_id: str | None = None
