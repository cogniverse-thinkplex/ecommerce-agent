from typing import Any

from app.agent.nodes.tool_proposal_node import ToolProposal
from app.agent.progress import AgentProgressEvent
from app.agent.runtime import BaselineAgentRuntime
from app.agent.state import CustomerAgentState
from app.tools.guarded_executor import GuardedRetailToolExecutor
from app.tools.retail_port import RetailToolDefinition, RetailToolResult


class OneShotGenerator:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, state, user_message):
        self.calls += 1
        if self.calls > 1:
            return None
        return ToolProposal(
            tool_name="get_order_details",
            arguments={"order_id": "#W1234567"},
            rationale="Read the requested order.",
        )


class OrderPort:
    @property
    def policy(self) -> str:
        return ""

    def list_tools(self):
        return [
            RetailToolDefinition(
                name="get_order_details",
                tool_type="read",
                description="Read an order.",
                parameters_schema={
                    "type": "object",
                    "required": ["order_id"],
                    "properties": {"order_id": {"type": "string"}},
                },
            )
        ]

    def call_tool(
        self, name: str, arguments: dict[str, Any], call_id: str | None = None
    ) -> RetailToolResult:
        return RetailToolResult(
            call_id=call_id or "call-1",
            name=name,
            content={"order_id": arguments["order_id"], "status": "pending"},
            raw_content='{"order_id":"#W1234567","status":"pending"}',
            error=False,
        )


def test_runtime_emits_safe_ordered_progress_events():
    runtime = BaselineAgentRuntime(
        GuardedRetailToolExecutor(OrderPort()),
        OneShotGenerator(),
    )
    events: list[AgentProgressEvent] = []

    result = runtime.run_until_blocked(
        CustomerAgentState(conversation_id="progress-1"),
        "查询订单 #W1234567",
        max_steps=2,
        progress_sink=events.append,
    )

    assert result.stopped_reason == "no_proposal"
    assert [event.stage for event in events] == [
        "planning",
        "order_lookup",
        "tool_completed",
        "planning",
        "composing",
    ]
    assert events[1].message == "正在读取订单信息"
    assert events[1].tool_name == "get_order_details"
    serialized = " ".join(event.model_dump_json() for event in events)
    assert "#W1234567" not in serialized
    assert '"status":"pending"' not in serialized


def test_runtime_progress_sink_is_optional():
    runtime = BaselineAgentRuntime(
        GuardedRetailToolExecutor(OrderPort()),
        OneShotGenerator(),
    )

    result = runtime.run_until_blocked(
        CustomerAgentState(conversation_id="progress-optional"),
        "查询订单 #W1234567",
        max_steps=2,
    )

    assert result.state.messages[-1].role == "assistant"
