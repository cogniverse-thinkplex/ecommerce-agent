from typing import Any

from app.agent.nodes.tool_node import ToolCallRequest
from app.agent.nodes.tool_proposal_node import ToolProposal
from app.agent.runtime import AgentTurnResult
from app.agent.session_service import AgentSessionService
from app.agent.state import ConversationMessage, CustomerAgentState, WriteObjective
from app.tools.guarded_executor import GuardedRetailToolExecutor
from app.tools.retail_port import RetailToolDefinition, RetailToolResult, ToolBackendInfo


def test_session_service_creates_session_and_records_user_message():
    service = AgentSessionService(_executor_with_tools([]))

    state = service.start_session("conv-1")
    state = service.add_user_message("conv-1", "I need help with an order")

    assert state.conversation_id == "conv-1"
    assert state.messages[-1].role == "user"
    assert state.messages[-1].content == "I need help with an order"


def test_session_service_run_turn_delegates_to_runtime_and_stores_returned_state():
    runtime = RecordingRuntime()
    service = AgentSessionService(_executor_with_tools([]), runtime=runtime)
    service.start_session("conv-1")

    result = service.run_turn("conv-1", "hello runtime")

    assert runtime.received_state == CustomerAgentState(conversation_id="conv-1")
    assert runtime.received_user_message == "hello runtime"
    assert result.state.messages[-1].content == "runtime handled the turn"
    assert service.get_session("conv-1").messages[-1].content == "runtime handled the turn"


def test_session_service_executes_read_tool_request():
    service = AgentSessionService(
        _executor_with_tools(
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
    service.start_session("conv-1")

    result = service.apply_tool_request(
        "conv-1",
        ToolCallRequest(
            name="get_order_details",
            arguments={"order_id": "#W2378156"},
            call_id="call-1",
        ),
    )

    assert result.executed is True
    assert result.state.messages[-2].role == "tool"
    assert result.state.messages[-2].tool_call_id == "call-1"
    assert result.state.messages[-1].role == "assistant"
    assert "订单 #W2378156" in result.state.messages[-1].content


def test_session_service_applies_tool_proposal():
    service = AgentSessionService(
        _executor_with_tools(
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
    service.start_session("conv-1")

    result = service.apply_tool_proposal(
        "conv-1",
        ToolProposal(
            tool_name="get_order_details",
            arguments={"order_id": "#W2378156"},
            rationale="Inspect order before answering.",
        ),
    )

    assert result.accepted is True
    assert result.tool_result is not None
    assert result.state.messages[-1].role == "tool"


def test_session_service_lists_events_with_optional_prefix_filter():
    service = AgentSessionService(
        _executor_with_tools(
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
    service.start_session("conv-1")
    service.apply_tool_request(
        "conv-1",
        ToolCallRequest(
            name="get_order_details",
            arguments={"order_id": "#W2378156"},
        ),
    )

    all_events = service.list_events("conv-1")
    policy_events = service.list_events("conv-1", event_type_prefix="policy_guard")

    assert [event.event_type for event in all_events] == [
        "policy_guard.allowed",
        "tool_executor.executed",
        "response.quality_checked",
    ]
    assert [event.event_type for event in policy_events] == ["policy_guard.allowed"]


def test_session_service_confirms_pending_write_then_executes_same_request():
    service = AgentSessionService(
        _executor_with_tools(
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
    service.start_session("conv-1")
    request = ToolCallRequest(
        name="cancel_pending_order",
        arguments={"order_id": "#W0000000", "reason": "ordered by mistake"},
        call_id="call-2",
    )

    pending = service.apply_tool_request("conv-1", request)
    confirmed = service.apply_confirmation_reply(
        "conv-1",
        confirmed=True,
        user_text="yes",
    )
    executed = service.apply_tool_request("conv-1", request)

    assert pending.confirmation_required is True
    assert confirmed.confirmed is True
    assert executed.executed is True
    assert executed.state.messages[-2].role == "tool"
    assert executed.state.messages[-1].role == "assistant"


def test_session_service_confirms_executes_and_continues_to_next_write():
    tools = [
        RetailToolDefinition(
            name="modify_pending_order_address",
            tool_type="write",
            description="",
            parameters_schema={},
        ),
        RetailToolDefinition(
            name="modify_pending_order_items",
            tool_type="write",
            description="",
            parameters_schema={},
        ),
    ]
    generator = SequencedProposalGenerator(
        [
            ToolProposal(
                tool_name="modify_pending_order_address",
                arguments={"order_id": "#W0000001", "city": "Charlotte"},
            ),
            ToolProposal(
                tool_name="modify_pending_order_items",
                arguments={"order_id": "#W0000001", "item_ids": ["old"]},
            ),
        ]
    )
    service = AgentSessionService(
        _executor_with_tools(tools),
        proposal_generator=generator,
    )
    service.start_session("conv-1")
    first = service.auto_run("conv-1", "update address and items", max_steps=2)

    result = service.confirm_pending_and_continue(
        "conv-1",
        confirmed=True,
        user_text="confirm address",
        objective="update address and items",
        max_steps=2,
    )

    assert first.state.confirmation.pending is not None
    assert result.executed.executed is True
    assert result.auto_run is not None
    assert result.auto_run.stopped_reason == "pending_confirmation"
    assert result.state.confirmation.pending is not None
    assert result.state.confirmation.pending.name == "modify_pending_order_items"
    continuation = [
        message.content
        for message in result.state.messages
        if message.role == "user" and message.content and "Completed write" in message.content
    ]
    assert continuation == [
        "Completed write: modify_pending_order_address. Continue only the remaining parts "
        "of the original objective without restarting completed lookups. Original objective: "
        "update address and items"
    ]


def test_session_service_continuation_uses_structured_next_objective():
    tools = [
        RetailToolDefinition(
            name="cancel_pending_order",
            tool_type="write",
            description="",
            parameters_schema={},
        ),
        RetailToolDefinition(
            name="modify_pending_order_address",
            tool_type="write",
            description="",
            parameters_schema={},
        ),
    ]
    generator = SequencedProposalGenerator(
        [
            ToolProposal(
                tool_name="cancel_pending_order",
                arguments={"order_id": "#W1", "reason": "ordered by mistake"},
            ),
            ToolProposal(
                tool_name="modify_pending_order_address",
                arguments={"order_id": "#W2", "city": "Boston"},
            ),
        ]
    )
    service = AgentSessionService(
        _executor_with_tools(tools),
        proposal_generator=generator,
    )
    state = service.start_session("conv-plan")
    service._sessions["conv-plan"] = state.model_copy(
        update={
            "objective_ledger": state.objective_ledger.model_copy(
                update={
                    "original_objective": "cancel one order and move another",
                    "locked_order_id": "#W1",
                    "write_plan": [
                        WriteObjective(
                            objective_id="cancel",
                            tool_name="cancel_pending_order",
                            order_id="#W1",
                        ),
                        WriteObjective(
                            objective_id="move",
                            tool_name="modify_pending_order_address",
                            order_id="#W2",
                            intent="move the other shipment",
                        ),
                    ],
                }
            )
        }
    )
    service.auto_run("conv-plan", "cancel one order and move another", max_steps=1)

    result = service.confirm_pending_and_continue(
        "conv-plan",
        confirmed=True,
        user_text="yes",
        objective="cancel one order and move another",
        max_steps=1,
    )

    assert result.auto_run is not None
    continuation = [
        message.content
        for message in result.state.messages
        if message.role == "user"
        and message.content
        and "NEXT_WRITE_OBJECTIVE" in message.content
    ]
    assert continuation == [
        "Continue the original objective using NEXT_WRITE_OBJECTIVE from the trusted "
        "OBJECTIVE_LEDGER. Resolve only that objective and do not repeat completed writes. "
        "Original objective: cancel one order and move another"
    ]
    assert "#W1" not in continuation[0]
    assert "reason" not in continuation[0]


def test_session_service_rejection_does_not_execute_or_continue():
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
    service = AgentSessionService(
        GuardedRetailToolExecutor(port),
        proposal_generator=SequencedProposalGenerator(
            [ToolProposal(tool_name="cancel_pending_order", arguments={"order_id": "#W1"})]
        ),
    )
    service.start_session("conv-1")
    service.auto_run("conv-1", "cancel it", max_steps=1)

    result = service.confirm_pending_and_continue(
        "conv-1",
        confirmed=False,
        user_text="no",
        objective="cancel it",
        max_steps=2,
    )

    assert result.executed is None
    assert result.auto_run is None
    assert not any(
        event.event_type == "tool_executor.executed" for event in result.state.events
    )


def test_session_service_rejects_missing_session_id():
    service = AgentSessionService(_executor_with_tools([]))

    try:
        service.add_user_message("missing", "hello")
    except KeyError as exc:
        assert str(exc) == "'Unknown conversation_id: missing'"
    else:
        raise AssertionError("Expected missing session to raise KeyError")


def test_session_service_reset_clears_sessions_and_rebuilds_executor():
    created_ports: list[RecordingPort] = []

    def executor_factory() -> GuardedRetailToolExecutor:
        port = RecordingPort(
            [
                RetailToolDefinition(
                    name=f"tool-{len(created_ports)}",
                    tool_type="read",
                    description="",
                    parameters_schema={},
                )
            ]
        )
        created_ports.append(port)
        return GuardedRetailToolExecutor(port)

    service = AgentSessionService(
        executor_factory(),
        executor_factory=executor_factory,
    )
    service.start_session("conv-1")

    result = service.reset_runtime_state()

    assert result.sessions_cleared == 1
    assert service.list_sessions() == []
    assert [tool.name for tool in service.list_tools()] == ["tool-1"]


def _executor_with_tools(
    tools: list[RetailToolDefinition],
) -> GuardedRetailToolExecutor:
    return GuardedRetailToolExecutor(RecordingPort(tools))


class RecordingPort:
    def __init__(self, tools: list[RetailToolDefinition]) -> None:
        self._tools = tools

    @property
    def backend(self) -> ToolBackendInfo:
        return ToolBackendInfo(
            kind="recording",
            name="recording-retail",
            managed_by_mcp=False,
        )

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
            raw_content='{"order_id": "#W2378156", "status": "delivered", "items": []}',
            error=False,
        )


class RecordingRuntime:
    def __init__(self) -> None:
        self.received_state: CustomerAgentState | None = None
        self.received_user_message: str | None = None

    def run_step(
        self,
        state: CustomerAgentState,
        user_message: str,
        *,
        append_no_proposal: bool = True,
    ) -> AgentTurnResult:
        self.received_state = state
        self.received_user_message = user_message
        next_state = state.model_copy(
            update={
                "messages": [
                    *state.messages,
                    ConversationMessage(
                        role="assistant",
                        content="runtime handled the turn",
                    ),
                ]
            }
        )
        return AgentTurnResult(state=next_state)


class SequencedProposalGenerator:
    def __init__(self, proposals: list[ToolProposal]) -> None:
        self.proposals = list(proposals)

    def generate(self, state, user_message):
        return self.proposals.pop(0) if self.proposals else None
