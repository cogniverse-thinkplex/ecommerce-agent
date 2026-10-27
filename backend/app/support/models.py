from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


BlockType = Literal[
    "text",
    "authentication_request",
    "order_summary",
    "product_summary",
    "profile_summary",
    "confirmation",
    "operation_result",
    "transfer_status",
    "recoverable_error",
    "policy_citations",
]


class SupportMessageBlock(BaseModel):
    type: BlockType
    title: str | None = None
    text: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class SupportConversation(BaseModel):
    conversation_id: str
    title: str
    status: str
    authenticated: bool
    group_id: str | None = None
    is_pinned: bool = False
    title_source: Literal["auto", "custom"] = "auto"
    message_count: int
    last_question_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class SupportConversationGroup(BaseModel):
    group_id: str
    name: str
    sort_order: int
    created_at: datetime
    updated_at: datetime


class SupportTurnResult(BaseModel):
    conversation_id: str
    blocks: list[SupportMessageBlock]
    pending_action_id: str | None = None
    handoff_ticket_id: str | None = None
    handoff_status: str | None = None

