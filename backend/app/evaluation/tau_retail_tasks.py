from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tau2.domains.retail.environment import get_tasks


@dataclass(frozen=True)
class ExpectedActionSummary:
    action_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class RetailTaskSummary:
    task_id: str
    reason_for_call: str
    known_info: str
    unknown_info: str
    task_instructions: str
    reward_basis: list[str]
    expected_actions: list[ExpectedActionSummary]


def load_retail_task_summaries(
    split: str | None = "base",
    limit: int | None = None,
) -> list[RetailTaskSummary]:
    tasks = get_tasks(task_split_name=split)
    if limit is not None:
        tasks = tasks[:limit]
    return [_summarize_task(task) for task in tasks]


def load_retail_task_summary(
    task_id: str,
    split: str | None = "base",
) -> RetailTaskSummary:
    for task in get_tasks(task_split_name=split):
        if task.id == task_id:
            return _summarize_task(task)
    raise KeyError(f"Unknown retail task_id: {task_id}")


def _summarize_task(task: Any) -> RetailTaskSummary:
    instructions = task.user_scenario.instructions
    criteria = task.evaluation_criteria
    actions = criteria.actions if criteria and criteria.actions else []
    reward_basis = criteria.reward_basis if criteria and criteria.reward_basis else []
    return RetailTaskSummary(
        task_id=task.id,
        reason_for_call=instructions.reason_for_call,
        known_info=instructions.known_info,
        unknown_info=instructions.unknown_info,
        task_instructions=instructions.task_instructions,
        reward_basis=[str(item.value if hasattr(item, "value") else item) for item in reward_basis],
        expected_actions=[
            ExpectedActionSummary(
                action_id=action.action_id,
                name=action.name,
                arguments=dict(action.arguments),
            )
            for action in actions
        ],
    )
