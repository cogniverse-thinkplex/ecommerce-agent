from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel


ProgressStage = Literal[
    "planning",
    "account_lookup",
    "order_lookup",
    "tool_running",
    "tool_completed",
    "composing",
    "awaiting_confirmation",
    "handoff_requested",
]


class AgentProgressEvent(BaseModel):
    stage: ProgressStage
    message: str
    tool_name: str | None = None
    completed: int | None = None
    total: int | None = None


ProgressSink = Callable[[AgentProgressEvent], None]


def emit_progress(
    sink: ProgressSink | None,
    event: AgentProgressEvent,
) -> None:
    if sink is not None:
        sink(event)


def tool_started_event(tool_name: str) -> AgentProgressEvent:
    if tool_name == "get_user_details":
        return AgentProgressEvent(
            stage="account_lookup",
            message="正在读取账户订单列表",
            tool_name=tool_name,
        )
    if tool_name == "get_order_details":
        return AgentProgressEvent(
            stage="order_lookup",
            message="正在读取订单信息",
            tool_name=tool_name,
        )
    return AgentProgressEvent(
        stage="tool_running",
        message="正在查询相关信息",
        tool_name=tool_name,
    )
