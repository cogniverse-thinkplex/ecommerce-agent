from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field


class EvaluationSummary(BaseModel):
    run_name: str
    run_type: str = "tau2"
    run_group: str = "adhoc"
    is_smoke: bool = False
    simulations: int
    task_ids: list[str]
    rewards: list[float]
    average_reward: float
    cost_available: bool = True
    total_cost: float | None
    average_cost: float | None
    exact_match_rate: float | None = None
    business_success_rate: float | None = None
    confirmation_gate_success_rate: float | None = None
    confirmed_outcome_success_rate: float | None = None
    average_matched_prefix_count: float | None = None
    average_step_count: float | None = None
    failure_categories: dict[str, int] = Field(default_factory=dict)


def summarize_run_dir(run_dir: Path) -> EvaluationSummary:
    results_file = run_dir / "results.json"
    if results_file.exists():
        return summarize_results_file(results_file, run_name=run_dir.name)
    runtime_subset_file = run_dir / "runtime_subset.json"
    if runtime_subset_file.exists():
        return summarize_runtime_subset_file(
            runtime_subset_file,
            run_name=run_dir.name,
        )
    raise KeyError(f"Evaluation run not found: {run_dir.name}")


def summarize_results_file(
    results_file: Path,
    run_name: str | None = None,
) -> EvaluationSummary:
    payload = json.loads(results_file.read_text())
    simulations = payload.get("simulations", [])
    rewards = [_extract_reward(simulation) for simulation in simulations]
    raw_costs = [
        simulation.get(cost_key)
        for simulation in simulations
        for cost_key in ("agent_cost", "user_cost")
    ]
    cost_available = bool(simulations) and all(cost is not None for cost in raw_costs)
    total_cost = (
        sum(_cost(cost) for cost in raw_costs) if cost_available else None
    )
    count = len(simulations)

    return EvaluationSummary(
        run_name=run_name or results_file.parent.name,
        run_type="tau2",
        run_group=_run_group(run_name or results_file.parent.name),
        is_smoke=_is_smoke_run(run_name or results_file.parent.name),
        simulations=count,
        task_ids=[str(simulation.get("task_id")) for simulation in simulations],
        rewards=rewards,
        average_reward=sum(rewards) / count if count else 0.0,
        total_cost=total_cost,
        average_cost=(total_cost / count if total_cost is not None and count else None),
        cost_available=cost_available,
    )


def summarize_runtime_subset_file(
    runtime_subset_file: Path,
    run_name: str | None = None,
) -> EvaluationSummary:
    payload = json.loads(runtime_subset_file.read_text())
    results = payload.get("results", [])
    count = len(results)
    exact_matches = [
        1.0 if result.get("check", {}).get("exact_match") else 0.0
        for result in results
    ]
    business_successes = [
        1.0
        if result.get("check", {}).get(
            "business_success",
            result.get("check", {}).get("exact_match", False),
        )
        else 0.0
        for result in results
    ]
    confirmation_gate_successes = [
        1.0
        if result.get("check", {}).get(
            "confirmation_gate_success",
            result.get("check", {}).get("business_success", False),
        )
        else 0.0
        for result in results
    ]
    confirmed_outcome_successes = [
        1.0
        if result.get("check", {}).get(
            "confirmed_outcome_success",
            result.get("check", {}).get("business_success_basis")
            == "confirmed_state_change",
        )
        else 0.0
        for result in results
    ]
    matched_prefix_counts = [
        float(result.get("check", {}).get("matched_prefix_count") or 0)
        for result in results
    ]
    step_counts = [float(result.get("step_count") or 0) for result in results]
    raw_costs = [result.get("cost") for result in results]
    cost_available = bool(results) and all(cost is not None for cost in raw_costs)
    total_cost = (
        sum(float(cost) for cost in raw_costs if cost is not None)
        if cost_available
        else None
    )
    resolved_run_name = run_name or str(payload.get("run_name") or runtime_subset_file.parent.name)
    return EvaluationSummary(
        run_name=resolved_run_name,
        run_type="runtime_subset",
        run_group=_run_group(resolved_run_name),
        is_smoke=_is_smoke_run(resolved_run_name),
        simulations=count,
        task_ids=[str(result.get("task_id")) for result in results],
        rewards=exact_matches,
        average_reward=sum(exact_matches) / count if count else 0.0,
        total_cost=total_cost,
        average_cost=(total_cost / count if total_cost is not None and count else None),
        cost_available=cost_available,
        exact_match_rate=sum(exact_matches) / count if count else 0.0,
        business_success_rate=(
            sum(business_successes) / count if count else 0.0
        ),
        confirmation_gate_success_rate=(
            sum(confirmation_gate_successes) / count if count else 0.0
        ),
        confirmed_outcome_success_rate=(
            sum(confirmed_outcome_successes) / count if count else 0.0
        ),
        average_matched_prefix_count=(
            sum(matched_prefix_counts) / count if count else 0.0
        ),
        average_step_count=sum(step_counts) / count if count else 0.0,
        failure_categories=_failure_categories(results),
    )


def _extract_reward(simulation: dict) -> float:
    reward_info = simulation.get("reward_info")
    if isinstance(reward_info, dict) and reward_info.get("reward") is not None:
        return float(reward_info["reward"])
    if simulation.get("reward") is not None:
        return float(simulation["reward"])
    return 0.0


def _cost(value: object) -> float:
    return float(value or 0.0)


def _failure_categories(results: list[dict]) -> dict[str, int]:
    categories: dict[str, int] = {}
    for result in results:
        category = result.get("failure_summary", {}).get("category")
        if category:
            categories[str(category)] = categories.get(str(category), 0) + 1
    return categories


def _run_group(run_name: str) -> str:
    if _is_smoke_run(run_name):
        return "smoke"
    if run_name.startswith("regression-"):
        return "regression"
    return "adhoc"


def _is_smoke_run(run_name: str) -> bool:
    return run_name.startswith("smoke-")
