from typing import Any

from app.agent.nodes.tool_proposal_node import ToolProposal, apply_tool_proposal
from app.agent.state import CustomerAgentState
from app.tools.guarded_executor import GuardedRetailToolExecutor
from app.tools.retail_port import RetailToolDefinition, RetailToolResult


def test_tool_proposal_node_executes_valid_read_proposal():
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

    result = apply_tool_proposal(
        CustomerAgentState(conversation_id="conv-1"),
        executor,
        ToolProposal(
            tool_name="get_order_details",
            arguments={"order_id": "#W2378156"},
            rationale="Need to inspect the order before answering.",
        ),
    )

    assert result.accepted is True
    assert result.tool_result is not None
    assert result.tool_result.executed is True
    assert result.state.messages[-1].role == "tool"


def test_tool_proposal_node_records_incomplete_proposal_without_execution():
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

    result = apply_tool_proposal(
        CustomerAgentState(conversation_id="conv-1"),
        executor,
        ToolProposal(
            tool_name="",
            arguments={},
            rationale="I am unsure what tool to use.",
        ),
    )

    assert result.accepted is False
    assert result.tool_result is None
    assert result.error == "Tool proposal must include tool_name"
    assert result.state.events[-1].event_type == "tool_proposal.rejected"


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
            raw_content='{"ok": true}',
            error=False,
        )
