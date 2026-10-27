from app.agent.state import ConfirmationState, CustomerAgentState
from app.policy.guard import (
    GuardDecisionType,
    check_tool_call,
    confirm_pending_action,
    fingerprint_action,
)
from app.tools.retail_port import RetailToolDefinition


def test_fingerprint_action_is_stable_for_argument_order():
    first = fingerprint_action(
        "modify_pending_order_address",
        {"zip": "98187", "order_id": "#W0000000"},
    )
    second = fingerprint_action(
        "modify_pending_order_address",
        {"order_id": "#W0000000", "zip": "98187"},
    )

    assert first == second


def test_policy_guard_allows_read_tools_without_confirmation():
    state = CustomerAgentState(conversation_id="conv-1")

    decision = check_tool_call(
        state,
        _tool("get_order_details", "read"),
        {"order_id": "#W2378156"},
    )

    assert decision.decision == GuardDecisionType.ALLOW
    assert decision.state.confirmation.pending is None


def test_policy_guard_requires_confirmation_for_unconfirmed_write_tool():
    state = CustomerAgentState(conversation_id="conv-1")

    decision = check_tool_call(
        state,
        _tool("cancel_pending_order", "write"),
        {"order_id": "#W0000000", "reason": "ordered by mistake"},
    )

    assert decision.decision == GuardDecisionType.REQUIRE_CONFIRMATION
    assert decision.state.confirmation.pending is not None
    assert decision.state.confirmation.pending.name == "cancel_pending_order"
    assert decision.state.events[-1].event_type == "policy_guard.requires_confirmation"


def test_policy_guard_allows_same_write_after_confirmation_only():
    state = CustomerAgentState(conversation_id="conv-1")
    arguments = {"order_id": "#W0000000", "reason": "ordered by mistake"}
    first = check_tool_call(state, _tool("cancel_pending_order", "write"), arguments)
    confirmed = confirm_pending_action(first.state)

    allowed = check_tool_call(
        confirmed,
        _tool("cancel_pending_order", "write"),
        {"reason": "ordered by mistake", "order_id": "#W0000000"},
    )
    changed = check_tool_call(
        confirmed,
        _tool("cancel_pending_order", "write"),
        {"order_id": "#W0000000", "reason": "no longer needed"},
    )

    assert allowed.decision == GuardDecisionType.ALLOW
    assert changed.decision == GuardDecisionType.REQUIRE_CONFIRMATION
    assert changed.state.confirmation.pending is not None
    assert changed.state.confirmation.pending.arguments["reason"] == "no longer needed"


def test_confirm_pending_action_records_fingerprint_and_clears_pending_action():
    pending = check_tool_call(
        CustomerAgentState(conversation_id="conv-1"),
        _tool("cancel_pending_order", "write"),
        {"order_id": "#W0000000", "reason": "ordered by mistake"},
    ).state

    confirmed = confirm_pending_action(pending)

    assert confirmed.confirmation.pending is None
    assert len(confirmed.confirmation.confirmed_fingerprints) == 1
    assert confirmed.events[-1].event_type == "policy_guard.confirmed"


def test_confirm_pending_action_without_pending_action_is_noop():
    state = CustomerAgentState(
        conversation_id="conv-1",
        confirmation=ConfirmationState(confirmed_fingerprints=["abc"]),
    )

    confirmed = confirm_pending_action(state)

    assert confirmed == state


def _tool(name: str, tool_type: str) -> RetailToolDefinition:
    return RetailToolDefinition(
        name=name,
        tool_type=tool_type,
        description="",
        parameters_schema={},
    )
