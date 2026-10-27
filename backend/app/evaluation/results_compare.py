from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from app.evaluation.results_summary import summarize_run_dir


class EvaluationComparisonItem(BaseModel):
    run_name: str
    run_type: str
    run_group: str = "adhoc"
    is_smoke: bool = False
    simulations: int
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


class EvaluationComparison(BaseModel):
    runs: list[EvaluationComparisonItem]


def compare_evaluation_runs(simulations_dir: Path) -> EvaluationComparison:
    if not simulations_dir.exists():
        return EvaluationComparison(runs=[])

    runs: list[EvaluationComparisonItem] = []
    for run_dir in sorted(path for path in simulations_dir.iterdir() if path.is_dir()):
        if not (run_dir / "results.json").exists() and not (
            run_dir / "runtime_subset.json"
        ).exists():
            continue
        summary = summarize_run_dir(run_dir)
        runs.append(
            EvaluationComparisonItem(
                run_name=summary.run_name,
                run_type=summary.run_type,
                run_group=summary.run_group,
                is_smoke=summary.is_smoke,
                simulations=summary.simulations,
                average_reward=summary.average_reward,
                total_cost=summary.total_cost,
                average_cost=summary.average_cost,
                cost_available=summary.cost_available,
                exact_match_rate=summary.exact_match_rate,
                business_success_rate=summary.business_success_rate,
                confirmation_gate_success_rate=summary.confirmation_gate_success_rate,
                confirmed_outcome_success_rate=summary.confirmed_outcome_success_rate,
                average_matched_prefix_count=summary.average_matched_prefix_count,
                average_step_count=summary.average_step_count,
                failure_categories=summary.failure_categories,
            )
        )
    return EvaluationComparison(runs=runs)
