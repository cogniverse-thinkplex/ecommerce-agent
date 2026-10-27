from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.agent.state import ConversationMessage, CustomerAgentState, record_tool_execution
from app.tools.guarded_executor import GuardedRetailToolExecutor


class ToolCallRequest(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    call_id: str | None = None


class ToolNodeResult(BaseModel):
    state: CustomerAgentState
    executed: bool
    confirmation_required: bool = False
    error: str | None = None


def apply_tool_call(
    state: CustomerAgentState,
    executor: GuardedRetailToolExecutor,
    request: ToolCallRequest,
) -> ToolNodeResult:
    execution = executor.call(
        state,
        request.name,
        request.arguments,
        call_id=request.call_id,
    )

    next_state = execution.state
    if execution.tool_result is not None:
        executed_event = next(
            (
                event
                for event in reversed(next_state.events)
                if event.event_type == "tool_executor.executed"
            ),
            None,
        )
        payload = executed_event.payload if executed_event is not None else {}
        next_state = record_tool_execution(
            next_state,
            tool_name=request.name,
            arguments=request.arguments,
            raw_content=execution.tool_result.raw_content,
            tool_type=str(payload.get("tool_type") or ""),
            error=bool(execution.tool_result.error),
            fingerprint=(
                str(payload["fingerprint"]) if payload.get("fingerprint") else None
            ),
        )
        next_state = _append_message(
            next_state,
            ConversationMessage(
                role="tool",
                content=execution.tool_result.raw_content,
                tool_call_id=execution.tool_result.call_id,
                tool_name=execution.tool_result.name,
            ),
        )
    elif execution.confirmation_required:
        pending = next_state.confirmation.pending
        if pending is not None:
            next_state = _append_message(
                next_state,
                ConversationMessage(
                    role="assistant",
                    content=(
                        "请确认是否执行这个写操作："
                        f"{pending.name}（fingerprint: {pending.fingerprint}）。"
                    ),
                ),
            )
    elif execution.error == "Retail identity access denied":
        next_state = _append_message(
            next_state,
            ConversationMessage(
                role="assistant",
                content="无法访问不属于当前账户的数据。",
            ),
        )

    return ToolNodeResult(
        state=next_state,
        executed=execution.executed,
        confirmation_required=execution.confirmation_required,
        error=execution.error,
    )


def _append_message(
    state: CustomerAgentState,
    message: ConversationMessage,
) -> CustomerAgentState:
    return state.model_copy(update={"messages": [*state.messages, message]})
