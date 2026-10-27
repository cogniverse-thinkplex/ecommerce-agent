from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.persistence.models import RegressionCaseRecord, RegressionCaseRunRecord


class RegressionCaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2000)
    origin_type: Literal["tau2", "issue", "feedback", "conversation", "manual"] = "manual"
    origin_id: str | None = None
    fixture_type: Literal["tau2_task", "conversation_replay"] = "tau2_task"
    fixture: dict[str, Any] = Field(default_factory=dict)
    expected: dict[str, Any] = Field(default_factory=dict)
    status: Literal["draft", "active", "retired"] = "draft"


class RegressionCaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    fixture: dict[str, Any] | None = None
    expected: dict[str, Any] | None = None
    status: Literal["draft", "active", "retired"] | None = None


class RegressionBatchCommand(BaseModel):
    case_ids: list[str] = Field(min_length=1, max_length=50)
    planner_type: Literal["rule", "llm"] = "rule"
    max_steps: int = Field(default=8, ge=1, le=20)
    verify_outcome_execution: bool = True


class RegressionCasePage(BaseModel):
    items: list[RegressionCaseRecord]
    total: int


class RegressionBatch(BaseModel):
    batch_id: str
    status: Literal["passed", "failed", "blocked"]
    planner_type: Literal["rule", "llm"]
    total_count: int
    passed_count: int
    failed_count: int
    blocked_count: int
    results: list[RegressionCaseRunRecord]
