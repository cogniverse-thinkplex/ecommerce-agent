from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.agent.state import CustomerAgentState
from app.evaluation.outcome_evaluator import (
    BusinessOutcomeCheck,
    evaluate_pending_outcome,
)
from app.evaluation.tau_retail_tasks import RetailTaskSummary


class SessionTaskCheck(BaseModel):
    task_id: str
    expected_actions: list[str]
    actual_actions: list[str]
    matched_prefix_count: int
    exact_match: bool
    business_success: bool = False
    confirmation_gate_success: bool = False
    confirmed_outcome_success: bool = False
    business_success_basis: Literal[
        "exact_match",
        "target_write_pending",
        "confirmed_state_change",
        "none",
    ] = "none"
    outcome: BusinessOutcomeCheck | None = None
    missing_actions: list[str]
    unexpected_actions: list[str]


def compare_session_to_task(
    state: CustomerAgentState,
    task: RetailTaskSummary,
) -> SessionTaskCheck:
    expected = [action.name for action in task.expected_actions]
    actual = [
        str(event.payload.get("tool"))
        for event in state.events
        if event.event_type == "tool_proposal.accepted" and event.payload.get("tool")
    ]
    matched_prefix_count = _matched_prefix_count(expected, actual)
    exact_match = actual == expected
    outcome = evaluate_pending_outcome(state, task)
    business_success = outcome.success if outcome.applicable else exact_match
    business_success_basis = (
        "target_write_pending"
        if outcome.applicable and outcome.success
        else "exact_match"
        if exact_match and not outcome.applicable
        else "none"
    )
    return SessionTaskCheck(
        task_id=task.task_id,
        expected_actions=expected,
        actual_actions=actual,
        matched_prefix_count=matched_prefix_count,
        exact_match=exact_match,
        business_success=business_success,
        confirmation_gate_success=outcome.success if outcome.applicable else False,
        confirmed_outcome_success=False,
        business_success_basis=business_success_basis,
        outcome=outcome,
        missing_actions=expected[matched_prefix_count:],
        unexpected_actions=actual[matched_prefix_count:],
    )


def _matched_prefix_count(expected: list[str], actual: list[str]) -> int:
    count = 0
    for expected_name, actual_name in zip(expected, actual):
        if expected_name != actual_name:
            break
        count += 1
    return count
