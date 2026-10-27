from app.agent.nodes.confirmation_node import (
    ConfirmationReply,
    apply_confirmation_reply,
)
from app.agent.state import CustomerAgentState
from app.policy.guard import check_tool_call
from app.tools.retail_port import RetailToolDefinition


def test_confirmation_node_confirms_pending_action_and_records_user_message():
    state = _state_with_pending_write()

    result = apply_confirmation_reply(
        state,
        ConfirmationReply(confirmed=True, user_text="yes, please do it"),
    )

    assert result.confirmed is True
    assert result.state.confirmation.pending is None
    assert len(result.state.confirmation.confirmed_fingerprints) == 1
    assert result.state.messages[-1].role == "user"
    assert result.state.messages[-1].content == "yes, please do it"
    assert result.state.events[-1].event_type == "policy_guard.confirmed"


def test_confirmation_node_rejects_pending_action_and_clears_it():
    state = _state_with_pending_write()

    result = apply_confirmation_reply(
        state,
        ConfirmationReply(confirmed=False, user_text="no, cancel that"),
    )

    assert result.confirmed is False
    assert result.state.confirmation.pending is None
    assert result.state.confirmation.confirmed_fingerprints == []
    assert result.state.messages[-1].role == "user"
    assert result.state.events[-1].event_type == "policy_guard.rejected"


def test_confirmation_node_without_pending_action_keeps_confirmation_state():
    state = CustomerAgentState(conversation_id="conv-1")

    result = apply_confirmation_reply(
        state,
        ConfirmationReply(confirmed=True, user_text="yes"),
    )

    assert result.confirmed is False
    assert result.error == "No pending action to confirm"
    assert result.state.confirmation == state.confirmation


def _state_with_pending_write() -> CustomerAgentState:
    decision = check_tool_call(
        CustomerAgentState(conversation_id="conv-1"),
        RetailToolDefinition(
            name="cancel_pending_order",
            tool_type="write",
            description="",
            parameters_schema={},
        ),
        {"order_id": "#W0000000", "reason": "ordered by mistake"},
    )
    return decision.state
