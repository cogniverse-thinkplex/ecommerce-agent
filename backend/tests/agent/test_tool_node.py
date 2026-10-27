from typing import Any

from app.agent.nodes.tool_node import ToolCallRequest, apply_tool_call
from app.agent.state import AgentEvent, CustomerAgentState
from app.policy.guard import confirm_pending_action
from app.tools.guarded_executor import GuardedRetailToolExecutor
from app.tools.retail_port import RetailToolDefinition, RetailToolResult


def test_tool_node_appends_tool_message_for_executed_read_call():
    executor = GuardedRetailToolExecutor(
        RecordingPort(
            [
                RetailToolDefinition(
                    name="get_order_details",
                    tool_type="read",
                    description="",
                    parameters_schema={},
                )
            ]
        )
    )

    result = apply_tool_call(
        CustomerAgentState(conversation_id="conv-1"),
        executor,
        ToolCallRequest(
            name="get_order_details",
            arguments={"order_id": "#W2378156"},
            call_id="call-1",
        ),
    )

    assert result.executed is True
    assert result.state.messages[-1].role == "tool"
    assert result.state.messages[-1].tool_call_id == "call-1"
    assert result.state.messages[-1].tool_name == "get_order_details"
    assert result.state.messages[-1].content == '{"order_id": "#W2378156"}'
    assert result.state.objective_ledger.inspected_order_ids == ["#W2378156"]


def test_tool_node_records_confirmation_prompt_for_unconfirmed_write_call():
    executor = GuardedRetailToolExecutor(
        RecordingPort(
            [
                RetailToolDefinition(
                    name="cancel_pending_order",
                    tool_type="write",
                    description="",
                    parameters_schema={},
                )
            ]
        )
    )

    result = apply_tool_call(
        CustomerAgentState(conversation_id="conv-1"),
        executor,
        ToolCallRequest(
            name="cancel_pending_order",
            arguments={"order_id": "#W0000000", "reason": "ordered by mistake"},
            call_id="call-2",
        ),
    )

    assert result.executed is False
    assert result.confirmation_required is True
    assert result.state.confirmation.pending is not None
    assert result.state.messages[-1].role == "assistant"
    assert "请确认" in result.state.messages[-1].content
    assert "cancel_pending_order" in result.state.messages[-1].content


def test_tool_node_executes_previously_confirmed_write_call():
    executor = GuardedRetailToolExecutor(
        RecordingPort(
            [
                RetailToolDefinition(
                    name="cancel_pending_order",
                    tool_type="write",
                    description="",
                    parameters_schema={},
                )
            ]
        )
    )
    arguments = {"order_id": "#W0000000", "reason": "ordered by mistake"}
    pending = apply_tool_call(
        CustomerAgentState(conversation_id="conv-1"),
        executor,
        ToolCallRequest(name="cancel_pending_order", arguments=arguments),
    )
    confirmed = confirm_pending_action(pending.state)

    result = apply_tool_call(
        confirmed,
        executor,
        ToolCallRequest(name="cancel_pending_order", arguments=arguments),
    )

    assert result.executed is True
    assert result.state.messages[-1].role == "tool"
    assert result.state.messages[-1].tool_name == "cancel_pending_order"
    assert result.state.objective_ledger.locked_order_id == "#W0000000"
    assert [write.name for write in result.state.objective_ledger.completed_writes] == [
        "cancel_pending_order"
    ]


def test_tool_node_returns_safe_message_for_cross_account_order():
    executor = GuardedRetailToolExecutor(
        CrossAccountOrderPort(
            [
                RetailToolDefinition(
                    name="get_order_details",
                    tool_type="read",
                    description="",
                    parameters_schema={},
                )
            ]
        )
    )
    state = CustomerAgentState(
        conversation_id="conv-linked",
        events=[
            AgentEvent(
                event_type="identity.platform_account_linked",
                payload={"user_id": "noah_brown_6181"},
            )
        ],
    )

    result = apply_tool_call(
        state,
        executor,
        ToolCallRequest(
            name="get_order_details",
            arguments={"order_id": "#W6893533"},
        ),
    )

    assert result.executed is False
    assert result.state.messages[-1].role == "assistant"
    assert result.state.messages[-1].content == "无法访问不属于当前账户的数据。"
    assert "ivan_santos_6635" not in result.state.model_dump_json()


class RecordingPort:
    def __init__(self, tools: list[RetailToolDefinition]) -> None:
        self._tools = tools

    @property
    def policy(self) -> str:
        return ""

    def list_tools(self) -> list[RetailToolDefinition]:
        return self._tools

    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        call_id: str | None = None,
    ) -> RetailToolResult:
        return RetailToolResult(
            call_id=call_id or "generated-call-id",
            name=name,
            content=arguments,
            raw_content='{"order_id": "#W2378156"}',
            error=False,
        )


class CrossAccountOrderPort(RecordingPort):
    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        call_id: str | None = None,
    ) -> RetailToolResult:
        return RetailToolResult(
            call_id=call_id or "generated-call-id",
            name=name,
            content={
                "order_id": arguments["order_id"],
                "user_id": "ivan_santos_6635",
            },
            raw_content=(
                '{"order_id":"#W6893533",'
                '"user_id":"ivan_santos_6635"}'
            ),
            error=False,
        )
