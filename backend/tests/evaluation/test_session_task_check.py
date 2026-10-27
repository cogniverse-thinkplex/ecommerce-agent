from app.agent.state import (
    AgentEvent,
    ConfirmationState,
    CustomerAgentState,
    PendingAction,
)
from app.evaluation.session_task_check import compare_session_to_task
from app.evaluation.tau_retail_tasks import ExpectedActionSummary, RetailTaskSummary


def test_compare_session_to_task_reports_exact_action_match():
    task = _task(["find_user_id_by_name_zip", "get_order_details"])
    state = _state_with_proposals(["find_user_id_by_name_zip", "get_order_details"])

    result = compare_session_to_task(state, task)

    assert result.exact_match is True
    assert result.business_success is True
    assert result.business_success_basis == "exact_match"
    assert result.matched_prefix_count == 2
    assert result.missing_actions == []
    assert result.unexpected_actions == []


def test_compare_session_to_task_reports_divergence_after_matched_prefix():
    task = _task(
        [
            "find_user_id_by_name_zip",
            "get_order_details",
            "get_product_details",
        ]
    )
    state = _state_with_proposals(["find_user_id_by_name_zip", "get_user_details"])

    result = compare_session_to_task(state, task)

    assert result.exact_match is False
    assert result.business_success is False
    assert result.business_success_basis == "none"
    assert result.matched_prefix_count == 1
    assert result.missing_actions == ["get_order_details", "get_product_details"]
    assert result.unexpected_actions == ["get_user_details"]


def test_compare_session_to_task_reports_business_success_for_target_write_gate():
    task = _task(
        [
            "find_user_id_by_name_zip",
            "get_product_details",
            "get_product_details",
            "return_delivered_order_items",
        ],
        final_arguments={"order_id": "#W2378156"},
    )
    state = _state_with_proposals(
        [
            "find_user_id_by_name_zip",
            "get_product_details",
            "get_user_details",
            "get_order_details",
            "return_delivered_order_items",
        ]
    ).model_copy(
        update={
            "confirmation": ConfirmationState(
                pending=PendingAction(
                    name="return_delivered_order_items",
                    arguments={"order_id": "#W2378156"},
                    fingerprint="return-demo",
                )
            )
        }
    )

    result = compare_session_to_task(state, task)

    assert result.exact_match is False
    assert result.business_success is True
    assert result.business_success_basis == "target_write_pending"
    assert result.outcome is not None
    assert result.outcome.arguments_match is True
    assert result.confirmation_gate_success is True
    assert result.confirmed_outcome_success is False


def _task(
    action_names: list[str],
    *,
    final_arguments: dict | None = None,
) -> RetailTaskSummary:
    return RetailTaskSummary(
        task_id="demo-task",
        reason_for_call="",
        known_info="",
        unknown_info="",
        task_instructions="",
        reward_basis=[],
        expected_actions=[
            ExpectedActionSummary(
                action_id=f"action-{index}",
                name=name,
                arguments=(final_arguments or {}) if index == len(action_names) - 1 else {},
            )
            for index, name in enumerate(action_names)
        ],
    )


def _state_with_proposals(action_names: list[str]) -> CustomerAgentState:
    return CustomerAgentState(
        conversation_id="conv-1",
        events=[
            AgentEvent(
                event_type="tool_proposal.accepted",
                payload={"tool": name},
            )
            for name in action_names
        ],
    )
