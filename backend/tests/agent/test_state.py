from app.agent.state import (
    ConfirmationState,
    CustomerAgentState,
    PendingAction,
    WriteObjective,
    append_event,
    initialize_objective_ledger,
    record_tool_execution,
)


def test_customer_agent_state_tracks_pending_confirmation_event():
    state = CustomerAgentState(conversation_id="conv-1")
    action = PendingAction(
        name="cancel_pending_order",
        arguments={"order_id": "#W0000000", "reason": "ordered by mistake"},
        fingerprint="cancel_pending_order:abc123",
    )

    next_state = append_event(
        state.model_copy(update={"confirmation": ConfirmationState(pending=action)}),
        "policy_guard.requires_confirmation",
        {"tool": action.name},
    )

    assert next_state.confirmation.pending == action
    assert next_state.events[-1].event_type == "policy_guard.requires_confirmation"
    assert next_state.events[-1].payload == {"tool": "cancel_pending_order"}


def test_objective_ledger_tracks_resolved_entities_and_completed_write():
    state = initialize_objective_ledger(
        CustomerAgentState(conversation_id="conv-ledger"),
        "update the address and backpack",
    )
    state = record_tool_execution(
        state,
        tool_name="get_order_details",
        arguments={"order_id": "#W1"},
        raw_content='{"order_id":"#W1","status":"pending"}',
        tool_type="read",
        error=False,
    )
    state = record_tool_execution(
        state,
        tool_name="get_product_details",
        arguments={"product_id": "P1"},
        raw_content=(
            '{"product_id":"P1","name":"Backpack","variants":{'
            '"V1":{"item_id":"V1","available":true,"options":{"size":"medium"}},'
            '"V2":{"item_id":"V2","available":false,"options":{"size":"large"}}}}'
        ),
        tool_type="read",
        error=False,
    )
    state = record_tool_execution(
        state,
        tool_name="modify_pending_order_address",
        arguments={"order_id": "#W1", "city": "Charlotte"},
        raw_content='{"order_id":"#W1"}',
        tool_type="write",
        error=False,
        fingerprint="write:abc",
    )

    assert state.objective_ledger.original_objective == "update the address and backpack"
    assert state.objective_ledger.inspected_order_ids == ["#W1"]
    assert state.objective_ledger.active_order_id == "#W1"
    assert state.objective_ledger.locked_order_id == "#W1"
    assert state.objective_ledger.resolved_products[0].product_id == "P1"
    assert state.objective_ledger.resolved_products[0].available_variants == [
        {"item_id": "V1", "options": {"size": "medium"}}
    ]
    assert state.objective_ledger.completed_writes[0].name == (
        "modify_pending_order_address"
    )


def test_objective_ledger_ignores_failed_and_duplicate_tool_executions():
    state = initialize_objective_ledger(
        CustomerAgentState(conversation_id="conv-ledger"),
        "cancel order",
    )
    for error in (True, False, False):
        state = record_tool_execution(
            state,
            tool_name="cancel_pending_order",
            arguments={"order_id": "#W1"},
            raw_content='{"order_id":"#W1"}',
            tool_type="write",
            error=error,
            fingerprint="cancel:abc",
        )

    assert len(state.objective_ledger.completed_writes) == 1
    assert state.objective_ledger.completed_writes[0].fingerprint == "cancel:abc"


def test_failed_order_lookup_records_canonical_id_without_inspecting_it():
    state = CustomerAgentState(conversation_id="conv-failed-order")

    for order_id in (" w8268610 ", "#W8268610"):
        state = record_tool_execution(
            state,
            tool_name="get_order_details",
            arguments={"order_id": order_id},
            raw_content="Order not found",
            tool_type="read",
            error=True,
        )

    assert state.objective_ledger.failed_order_ids == ["#W8268610"]
    assert state.objective_ledger.inspected_order_ids == []


def test_failed_order_lookup_does_not_trust_malformed_id():
    state = record_tool_execution(
        CustomerAgentState(conversation_id="conv-malformed-order"),
        tool_name="get_order_details",
        arguments={"order_id": "W82-68610"},
        raw_content="Order not found",
        tool_type="read",
        error=True,
    )

    assert state.objective_ledger.failed_order_ids == []
    assert state.objective_ledger.inspected_order_ids == []


def test_successful_user_details_records_canonical_known_orders():
    state = record_tool_execution(
        CustomerAgentState(conversation_id="conv-known-orders"),
        tool_name="get_user_details",
        arguments={"user_id": "user-1"},
        raw_content=(
            '{"user_id":"user-1","orders":['
            '"W8268610",{"order_id":"#w2702727"},"bad-order","#W8268610"]}'
        ),
        tool_type="read",
        error=False,
    )

    assert state.objective_ledger.known_order_ids == ["#W8268610", "#W2702727"]


def test_successful_user_details_accepts_order_mapping():
    state = record_tool_execution(
        CustomerAgentState(conversation_id="conv-order-map"),
        tool_name="get_user_details",
        arguments={"user_id": "user-1"},
        raw_content='{"orders":{"W8268610":{},"#w2702727":{}}}',
        tool_type="read",
        error=False,
    )

    assert state.objective_ledger.known_order_ids == ["#W8268610", "#W2702727"]


def test_successful_order_lookup_moves_id_from_failed_to_inspected():
    state = CustomerAgentState(conversation_id="conv-recovered-order")
    state = record_tool_execution(
        state,
        tool_name="get_order_details",
        arguments={"order_id": "W8268610"},
        raw_content="Order not found",
        tool_type="read",
        error=True,
    )
    state = record_tool_execution(
        state,
        tool_name="get_order_details",
        arguments={"order_id": "W8268610"},
        raw_content='{"order_id":"#w8268610","status":"pending"}',
        tool_type="read",
        error=False,
    )

    assert state.objective_ledger.failed_order_ids == []
    assert state.objective_ledger.inspected_order_ids == ["#W8268610"]


def test_unrelated_failure_does_not_change_order_identity_state():
    state = record_tool_execution(
        CustomerAgentState(conversation_id="conv-unrelated-failure"),
        tool_name="get_product_details",
        arguments={"product_id": "P1"},
        raw_content="Product not found",
        tool_type="read",
        error=True,
    )

    assert state.objective_ledger.failed_order_ids == []
    assert state.objective_ledger.known_order_ids == []
    assert state.objective_ledger.inspected_order_ids == []


def test_successful_write_completes_one_duplicate_objective_and_hands_off_lock():
    state = _state_with_plan(
        [
            WriteObjective(
                objective_id="first",
                tool_name="modify_pending_order_items",
                order_id="#W1",
            ),
            WriteObjective(
                objective_id="second",
                tool_name="modify_pending_order_items",
                order_id="#W2",
            ),
        ],
        locked_order_id="#W1",
    )

    state = record_tool_execution(
        state,
        tool_name="modify_pending_order_items",
        arguments={"order_id": "#W1", "item_ids": ["I1"]},
        raw_content='{"order_id":"#W1"}',
        tool_type="write",
        error=False,
        fingerprint="items:first",
    )

    assert [item.status for item in state.objective_ledger.write_plan] == [
        "completed",
        "pending",
    ]
    assert state.objective_ledger.write_plan[0].completed_fingerprint == "items:first"
    assert state.objective_ledger.write_plan[1].completed_fingerprint is None
    assert state.objective_ledger.locked_order_id == "#W2"


def test_write_plan_releases_lock_when_next_objective_order_is_unknown():
    state = _state_with_plan(
        [
            WriteObjective(
                objective_id="cancel",
                tool_name="cancel_pending_order",
                order_id="#W1",
            ),
            WriteObjective(
                objective_id="address",
                tool_name="modify_pending_order_address",
            ),
        ],
        locked_order_id="#W1",
    )

    state = record_tool_execution(
        state,
        tool_name="cancel_pending_order",
        arguments={"order_id": "#W1", "reason": "ordered by mistake"},
        raw_content='{"order_id":"#W1"}',
        tool_type="write",
        error=False,
        fingerprint="cancel:first",
    )

    assert state.objective_ledger.write_plan[0].status == "completed"
    assert state.objective_ledger.locked_order_id is None


def test_write_plan_does_not_advance_or_change_lock_on_failure_or_mismatch():
    initial = _state_with_plan(
        [
            WriteObjective(
                objective_id="address",
                tool_name="modify_pending_order_address",
                order_id="#W1",
            )
        ],
        locked_order_id="#W1",
    )
    failed = record_tool_execution(
        initial,
        tool_name="modify_pending_order_address",
        arguments={"order_id": "#W1"},
        raw_content=None,
        tool_type="write",
        error=True,
        fingerprint="address:failed",
    )
    mismatched = record_tool_execution(
        initial,
        tool_name="cancel_pending_order",
        arguments={"order_id": "#W2"},
        raw_content='{"order_id":"#W2"}',
        tool_type="write",
        error=False,
        fingerprint="cancel:other",
    )

    assert failed.objective_ledger.write_plan[0].status == "pending"
    assert mismatched.objective_ledger.write_plan[0].status == "pending"
    assert failed.objective_ledger.locked_order_id == "#W1"
    assert mismatched.objective_ledger.locked_order_id == "#W1"


def _state_with_plan(
    objectives: list[WriteObjective],
    *,
    locked_order_id: str | None,
) -> CustomerAgentState:
    state = CustomerAgentState(conversation_id="conv-plan")
    return state.model_copy(
        update={
            "objective_ledger": state.objective_ledger.model_copy(
                update={
                    "write_plan": objectives,
                    "locked_order_id": locked_order_id,
                }
            )
        }
    )
