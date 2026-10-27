from app.agent.state import AgentEvent, ConfirmationState, CustomerAgentState, PendingAction
from app.evaluation.outcome_evaluator import (
    evaluate_executed_outcome,
    evaluate_pending_outcome,
    with_execution_evidence,
)
from app.evaluation.tau_retail_tasks import ExpectedActionSummary, RetailTaskSummary
from app.policy.guard import fingerprint_action


def test_pending_outcome_requires_exact_target_arguments():
    task = _task(
        "return_delivered_order_items",
        {
            "order_id": "#W1234567",
            "item_ids": ["item-1", "item-2"],
            "payment_method_id": "card-1",
        },
    )
    state = _pending_state(
        "return_delivered_order_items",
        {
            "order_id": "#W1234567",
            "item_ids": ["item-1", "item-2"],
            "payment_method_id": "card-1",
        },
    )

    outcome = evaluate_pending_outcome(state, task)

    assert outcome.applicable is True
    assert outcome.target_action == "return_delivered_order_items"
    assert outcome.tool_match is True
    assert outcome.arguments_match is True
    assert outcome.argument_mismatches == []
    assert outcome.confirmation_gate_reached is True
    assert outcome.confirmation_executed is False
    assert outcome.state_changed is None
    assert outcome.success is True
    assert outcome.status == "pending_confirmation_verified"


def test_pending_outcome_rejects_correct_tool_with_wrong_arguments():
    task = _task(
        "modify_pending_order_address",
        {"order_id": "#W1234567", "address2": "Suite 641"},
    )
    state = _pending_state(
        "modify_pending_order_address",
        {"order_id": "#W1234567", "address2": "Suite 146"},
    )

    outcome = evaluate_pending_outcome(state, task)

    assert outcome.tool_match is True
    assert outcome.arguments_match is False
    assert outcome.argument_mismatches == ["address2"]
    assert outcome.success is False
    assert outcome.status == "argument_mismatch"


def test_pending_outcome_reports_target_not_reached():
    outcome = evaluate_pending_outcome(
        CustomerAgentState(conversation_id="conv-1"),
        _task("cancel_pending_order", {"order_id": "#W1234567"}),
    )

    assert outcome.applicable is True
    assert outcome.confirmation_gate_reached is False
    assert outcome.success is False
    assert outcome.status == "target_not_reached"


def test_pending_outcome_is_not_applicable_without_expected_write():
    task = _task("get_order_details", {"order_id": "#W1234567"})

    outcome = evaluate_pending_outcome(
        CustomerAgentState(conversation_id="conv-1"),
        task,
    )

    assert outcome.applicable is False
    assert outcome.target_action is None
    assert outcome.status == "not_applicable"


def test_execution_evidence_requires_successful_write_and_database_change():
    pending = evaluate_pending_outcome(
        _pending_state("cancel_pending_order", {"order_id": "#W1234567"}),
        _task("cancel_pending_order", {"order_id": "#W1234567"}),
    )

    verified = with_execution_evidence(
        pending,
        executed=True,
        tool_error=False,
        state_changed=True,
    )
    unchanged = with_execution_evidence(
        pending,
        executed=True,
        tool_error=False,
        state_changed=False,
    )

    assert verified.success is True
    assert verified.confirmation_executed is True
    assert verified.state_changed is True
    assert verified.status == "confirmed_state_verified"
    assert unchanged.success is False
    assert unchanged.status == "state_unchanged"


def test_execution_evidence_distinguishes_unavailable_state_verification():
    pending = evaluate_pending_outcome(
        _pending_state("cancel_pending_order", {"order_id": "#W1234567"}),
        _task("cancel_pending_order", {"order_id": "#W1234567"}),
    )

    unavailable = with_execution_evidence(
        pending,
        executed=True,
        tool_error=False,
        state_changed=None,
    )

    assert unavailable.success is False
    assert unavailable.status == "state_verification_unavailable"


def test_executed_outcome_requires_every_expected_write_action():
    address = ExpectedActionSummary(
        action_id="address",
        name="modify_pending_order_address",
        arguments={"order_id": "#W1", "city": "Charlotte"},
    )
    items = ExpectedActionSummary(
        action_id="items",
        name="modify_pending_order_items",
        arguments={"order_id": "#W1", "item_ids": ["old"], "new_item_ids": ["new"]},
    )
    task = RetailTaskSummary(
        task_id="multi",
        reason_for_call="",
        known_info="",
        unknown_info="",
        task_instructions="",
        reward_basis=[],
        expected_actions=[address, items],
    )
    state = CustomerAgentState(
        conversation_id="conv-1",
        events=[
            AgentEvent(
                event_type="tool_executor.executed",
                payload={
                    "tool": action.name,
                    "tool_type": "write",
                    "error": False,
                    "fingerprint": fingerprint_action(action.name, action.arguments),
                },
            )
            for action in (address, items)
        ],
    )

    complete = evaluate_executed_outcome(state, task)
    incomplete = evaluate_executed_outcome(
        state.model_copy(update={"events": state.events[:1]}),
        task,
    )

    assert complete.success is True
    assert complete.confirmation_executed is True
    assert complete.expected_write_count == 2
    assert complete.executed_write_count == 2
    assert incomplete.success is False
    assert incomplete.executed_write_count == 1


def _task(action_name: str, arguments: dict) -> RetailTaskSummary:
    return RetailTaskSummary(
        task_id="demo",
        reason_for_call="",
        known_info="",
        unknown_info="",
        task_instructions="",
        reward_basis=[],
        expected_actions=[
            ExpectedActionSummary(
                action_id="action-1",
                name=action_name,
                arguments=arguments,
            )
        ],
    )


def _pending_state(action_name: str, arguments: dict) -> CustomerAgentState:
    return CustomerAgentState(
        conversation_id="conv-1",
        confirmation=ConfirmationState(
            pending=PendingAction(
                name=action_name,
                arguments=arguments,
                fingerprint="fingerprint",
            )
        ),
    )
