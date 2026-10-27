from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agent.state import CustomerAgentState
from app.evaluation.tau_retail_tasks import RetailTaskSummary
from app.policy.guard import fingerprint_action


OutcomeStatus = Literal[
    "not_applicable",
    "target_not_reached",
    "tool_mismatch",
    "argument_mismatch",
    "pending_confirmation_verified",
    "confirmed_state_verified",
    "execution_failed",
    "state_unchanged",
    "state_verification_unavailable",
]


WRITE_ACTION_NAMES = {
    "cancel_pending_order",
    "exchange_delivered_order_items",
    "modify_pending_order_address",
    "modify_pending_order_items",
    "modify_pending_order_payment",
    "modify_user_address",
    "return_delivered_order_items",
}


class BusinessOutcomeCheck(BaseModel):
    applicable: bool = False
    target_action: str | None = None
    expected_arguments: dict[str, Any] = Field(default_factory=dict)
    actual_arguments: dict[str, Any] = Field(default_factory=dict)
    tool_match: bool = False
    arguments_match: bool = False
    argument_mismatches: list[str] = Field(default_factory=list)
    confirmation_gate_reached: bool = False
    confirmation_executed: bool = False
    state_changed: bool | None = None
    expected_write_count: int = 0
    executed_write_count: int = 0
    success: bool = False
    status: OutcomeStatus = "not_applicable"


def evaluate_executed_outcome(
    state: CustomerAgentState,
    task: RetailTaskSummary,
) -> BusinessOutcomeCheck:
    expected_writes = [
        action for action in task.expected_actions if action.name in WRITE_ACTION_NAMES
    ]
    if not expected_writes:
        return BusinessOutcomeCheck()

    executed_fingerprints = {
        str(event.payload.get("fingerprint"))
        for event in state.events
        if event.event_type == "tool_executor.executed"
        and event.payload.get("tool_type") == "write"
        and not event.payload.get("error")
        and event.payload.get("fingerprint")
    }
    matched = [
        action
        for action in expected_writes
        if fingerprint_action(action.name, action.arguments) in executed_fingerprints
    ]
    target = expected_writes[-1]
    complete = len(matched) == len(expected_writes)
    return BusinessOutcomeCheck(
        applicable=True,
        target_action=target.name,
        expected_arguments=target.arguments,
        tool_match=complete,
        arguments_match=complete,
        confirmation_gate_reached=complete,
        confirmation_executed=complete,
        expected_write_count=len(expected_writes),
        executed_write_count=len(matched),
        success=complete,
        status="pending_confirmation_verified" if complete else "target_not_reached",
    )


def evaluate_pending_outcome(
    state: CustomerAgentState,
    task: RetailTaskSummary,
) -> BusinessOutcomeCheck:
    target = next(
        (
            action
            for action in reversed(task.expected_actions)
            if action.name in WRITE_ACTION_NAMES
        ),
        None,
    )
    if target is None:
        return BusinessOutcomeCheck()

    executed = evaluate_executed_outcome(state, task)
    if executed.confirmation_executed:
        return executed

    pending = state.confirmation.pending
    if pending is None:
        return executed

    tool_match = pending.name == target.name
    mismatches = _argument_mismatches(target.arguments, pending.arguments)
    arguments_match = not mismatches
    if not tool_match:
        status: OutcomeStatus = "tool_mismatch"
    elif not arguments_match:
        status = "argument_mismatch"
    else:
        status = "pending_confirmation_verified"
    return BusinessOutcomeCheck(
        applicable=True,
        target_action=target.name,
        expected_arguments=target.arguments,
        actual_arguments=pending.arguments,
        tool_match=tool_match,
        arguments_match=arguments_match,
        argument_mismatches=mismatches,
        confirmation_gate_reached=tool_match,
        expected_write_count=executed.expected_write_count,
        executed_write_count=executed.executed_write_count,
        success=tool_match and arguments_match,
        status=status,
    )


def with_execution_evidence(
    outcome: BusinessOutcomeCheck,
    *,
    executed: bool,
    tool_error: bool,
    state_changed: bool | None,
) -> BusinessOutcomeCheck:
    if not outcome.success or not executed or tool_error:
        return outcome.model_copy(
            update={
                "confirmation_executed": executed,
                "state_changed": state_changed,
                "success": False,
                "status": "execution_failed",
            }
        )
    if state_changed is None:
        return outcome.model_copy(
            update={
                "confirmation_executed": True,
                "state_changed": None,
                "success": False,
                "status": "state_verification_unavailable",
            }
        )
    if state_changed is False:
        return outcome.model_copy(
            update={
                "confirmation_executed": True,
                "state_changed": state_changed,
                "success": False,
                "status": "state_unchanged",
            }
        )
    return outcome.model_copy(
        update={
            "confirmation_executed": True,
            "state_changed": True,
            "success": True,
            "status": "confirmed_state_verified",
        }
    )


def _argument_mismatches(
    expected: dict[str, Any],
    actual: dict[str, Any],
) -> list[str]:
    return sorted(
        key
        for key in set(expected) | set(actual)
        if expected.get(key) != actual.get(key) or key not in expected or key not in actual
    )
