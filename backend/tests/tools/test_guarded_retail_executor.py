from typing import Any

from app.agent.state import AgentEvent, ConversationMessage, CustomerAgentState
from app.policy.guard import confirm_pending_action
from app.tools.guarded_executor import GuardedRetailToolExecutor
from app.tools.retail_port import RetailToolDefinition, RetailToolResult


def test_guarded_executor_runs_read_tool_immediately():
    port = RecordingPort(
        [
            RetailToolDefinition(
                name="get_order_details",
                tool_type="read",
                description="",
                parameters_schema={},
            )
        ]
    )
    executor = GuardedRetailToolExecutor(port)

    result = executor.call(
        CustomerAgentState(conversation_id="conv-1"),
        "get_order_details",
        {"order_id": "#W2378156"},
    )

    assert result.executed is True
    assert result.tool_result is not None
    assert result.tool_result.content == {"ok": True}
    assert port.calls == [("get_order_details", {"order_id": "#W2378156"})]


def test_guarded_executor_exposes_policy_and_tool_catalog():
    tool = RetailToolDefinition(
        name="get_order_details",
        tool_type="read",
        description="",
        parameters_schema={},
    )
    executor = GuardedRetailToolExecutor(RecordingPort([tool], policy="Retail policy"))

    assert executor.policy == "Retail policy"
    assert executor.list_tools() == [tool]


def test_guarded_executor_blocks_write_until_confirmed():
    port = RecordingPort(
        [
            RetailToolDefinition(
                name="cancel_pending_order",
                tool_type="write",
                description="",
                parameters_schema={},
            )
        ]
    )
    executor = GuardedRetailToolExecutor(port)
    state = CustomerAgentState(conversation_id="conv-1")
    arguments = {"order_id": "#W0000000", "reason": "ordered by mistake"}

    pending = executor.call(state, "cancel_pending_order", arguments)
    assert port.calls == []

    confirmed_state = confirm_pending_action(pending.state)
    executed = executor.call(confirmed_state, "cancel_pending_order", arguments)

    assert pending.executed is False
    assert pending.tool_result is None
    assert pending.confirmation_required is True
    assert port.calls == [("cancel_pending_order", arguments)]
    assert executed.executed is True
    assert executed.tool_result is not None


def test_guarded_executor_records_write_state_change_evidence():
    port = StateTrackingPort()
    executor = GuardedRetailToolExecutor(port)
    arguments = {"order_id": "#W0000000", "reason": "ordered by mistake"}
    pending = executor.call(
        CustomerAgentState(conversation_id="conv-1"),
        "cancel_pending_order",
        arguments,
    )

    executed = executor.call(
        confirm_pending_action(pending.state),
        "cancel_pending_order",
        arguments,
    )

    event = executed.state.events[-1]
    assert event.event_type == "tool_executor.executed"
    assert event.payload["state_verification_available"] is True
    assert event.payload["state_changed"] is True


def test_guarded_executor_rejects_unknown_tool_name():
    executor = GuardedRetailToolExecutor(RecordingPort([]))

    result = executor.call(
        CustomerAgentState(conversation_id="conv-1"),
        "unknown_tool",
        {},
    )

    assert result.executed is False
    assert result.error == "Unknown tool: unknown_tool"
    assert result.state.events[-1].event_type == "tool_executor.unknown_tool"


def test_guarded_executor_blocks_cross_account_user_lookup():
    port = RecordingPort(
        [_tool("get_user_details", "read")],
    )
    executor = GuardedRetailToolExecutor(port)

    result = executor.call(
        _linked_state("ivan_santos_6635"),
        "get_user_details",
        {"user_id": "anya_garcia_3271"},
    )

    assert result.executed is False
    assert result.error == "Retail identity access denied"
    assert port.calls == []
    assert result.state.events[-1].event_type == "policy_guard.identity_denied"


def test_guarded_executor_hides_cross_account_order_result():
    port = RecordingPort(
        [_tool("get_order_details", "read")],
        result_content={"order_id": "#W4140680", "user_id": "anya_garcia_3271"},
    )
    executor = GuardedRetailToolExecutor(port)

    result = executor.call(
        _linked_state("ivan_santos_6635"),
        "get_order_details",
        {"order_id": "#W4140680"},
    )

    assert result.executed is False
    assert result.tool_result is None
    assert result.error == "Retail identity access denied"
    assert result.state.events[-1].event_type == "policy_guard.identity_denied"


def test_guarded_executor_blocks_cross_account_write_before_confirmation():
    port = RecordingPort([_tool("cancel_pending_order", "write")])
    state = _linked_state("ivan_santos_6635").model_copy(
        update={
            "messages": [
                ConversationMessage(
                    role="tool",
                    tool_name="get_order_details",
                    content=(
                        '{"order_id":"#W4140680",'
                        '"user_id":"anya_garcia_3271"}'
                    ),
                )
            ]
        }
    )
    executor = GuardedRetailToolExecutor(port)

    result = executor.call(
        state,
        "cancel_pending_order",
        {"order_id": "#W4140680", "reason": "mistake"},
    )

    assert result.executed is False
    assert result.confirmation_required is False
    assert result.error == "Retail identity access denied"
    assert port.calls == []


class RecordingPort:
    def __init__(
        self,
        tools: list[RetailToolDefinition],
        policy: str = "",
        result_content: dict[str, Any] | None = None,
    ) -> None:
        self._tools = tools
        self._policy = policy
        self._result_content = result_content or {"ok": True}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    @property
    def policy(self) -> str:
        return self._policy

    def list_tools(self) -> list[RetailToolDefinition]:
        return self._tools

    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        call_id: str | None = None,
    ) -> RetailToolResult:
        self.calls.append((name, arguments))
        return RetailToolResult(
            call_id=call_id or "call-1",
            name=name,
            content=self._result_content,
            raw_content=__import__("json").dumps(self._result_content),
            error=False,
        )


class StateTrackingPort(RecordingPort):
    def __init__(self) -> None:
        super().__init__(
            [
                RetailToolDefinition(
                    name="cancel_pending_order",
                    tool_type="write",
                    description="",
                    parameters_schema={},
                )
            ]
        )
        self._version = 0

    def db_hash(self) -> str:
        return f"state-{self._version}"

    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        call_id: str | None = None,
    ) -> RetailToolResult:
        result = super().call_tool(name, arguments, call_id=call_id)
        self._version += 1
        return result


def _linked_state(retail_user_id: str) -> CustomerAgentState:
    return CustomerAgentState(
        conversation_id="conv-linked",
        events=[
            AgentEvent(
                event_type="identity.platform_account_linked",
                payload={"user_id": retail_user_id},
            )
        ],
    )


def _tool(name: str, tool_type: str) -> RetailToolDefinition:
    return RetailToolDefinition(
        name=name,
        tool_type=tool_type,
        description="",
        parameters_schema={},
    )
