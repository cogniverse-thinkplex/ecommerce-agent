from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from app.evaluation.runtime_task_runner import (
    RuntimePlannerType,
    run_retail_task_subset,
    save_runtime_task_subset_artifact,
)


class RegressionScenario(BaseModel):
    task_id: str
    scenario: str
    step_budget: int


REGRESSION_SCENARIOS = [
    RegressionScenario(task_id="0", scenario="exchange", step_budget=6),
    RegressionScenario(task_id="52", scenario="exchange", step_budget=10),
    RegressionScenario(task_id="2", scenario="return", step_budget=12),
    RegressionScenario(task_id="48", scenario="return", step_budget=10),
    RegressionScenario(task_id="38", scenario="cancel", step_budget=8),
    RegressionScenario(task_id="69", scenario="cancel", step_budget=10),
    RegressionScenario(task_id="17", scenario="address_update", step_budget=8),
    RegressionScenario(task_id="71", scenario="address_update", step_budget=10),
    RegressionScenario(task_id="40", scenario="payment_update", step_budget=8),
]


def run_runtime_regression(
    *,
    simulations_dir: Path,
    planner_type: RuntimePlannerType = "rule",
    run_name: str | None = None,
    report_path: Path | None = None,
) -> Path:
    resolved_run_name = run_name or f"regression-{planner_type}-{_timestamp()}"
    task_ids = [scenario.task_id for scenario in REGRESSION_SCENARIOS]
    task_step_budgets = {
        scenario.task_id: scenario.step_budget for scenario in REGRESSION_SCENARIOS
    }
    task_scenarios = {
        scenario.task_id: scenario.scenario for scenario in REGRESSION_SCENARIOS
    }
    results = run_retail_task_subset(
        task_ids,
        max_steps=6,
        task_step_budgets=task_step_budgets,
        planner_type=planner_type,
        verify_outcome_execution=True,
    )
    artifact = save_runtime_task_subset_artifact(
        results,
        output_dir=simulations_dir,
        run_name=resolved_run_name,
        max_steps=6,
        task_step_budgets=task_step_budgets,
        task_scenarios=task_scenarios,
    )
    artifact_path = Path(artifact.path)
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            build_regression_markdown_report(json.loads(artifact_path.read_text()))
        )
    return artifact_path


def build_regression_markdown_report(artifact: dict) -> str:
    summary = artifact.get("summary") or {}
    total_tasks = int(summary.get("total_tasks") or 0)
    business_success_count = int(summary.get("business_success_count") or 0)
    confirmation_gate_success_count = int(
        summary.get("confirmation_gate_success_count") or 0
    )
    confirmed_outcome_success_count = int(
        summary.get("confirmed_outcome_success_count") or 0
    )
    scenario_metrics = summary.get("scenario_metrics") or {}
    lines = [
        f"# Runtime Regression Report: {artifact.get('run_name', 'unknown')}",
        "",
        f"- Planner: `{artifact.get('planner_type', 'unknown')}`",
        f"- Business success: `{business_success_count}/{total_tasks}`",
        f"- Confirmation gate success: `{confirmation_gate_success_count}/{total_tasks}`",
        f"- Confirmed outcome success: `{confirmed_outcome_success_count}/{total_tasks}`",
        f"- Exact match: `{int(summary.get('exact_match_count') or 0)}/{total_tasks}`",
        f"- Average steps: `{float(summary.get('average_step_count') or 0):.2f}`",
        f"- Total cost: `{_format_cost(summary.get('total_cost'))}`",
        f"- Tokens: `{int(summary.get('prompt_tokens') or 0)} input / "
        f"{int(summary.get('completion_tokens') or 0)} output / "
        f"{int(summary.get('total_tokens') or 0)} total`",
        "- Estimated list cost: `"
        + _format_cny(summary.get("total_estimated_list_cost_cny"))
        + "`",
        "",
        "## Scenario Metrics",
        "",
        "| Scenario | Tasks | Business success | Confirmation gate | Confirmed outcome | Exact match | Avg steps | Total cost |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for scenario_name in scenario_metrics:
        metric = scenario_metrics.get(scenario_name)
        if metric is None:
            continue
        lines.append(
            f"| {scenario_name} | {metric['task_count']} | "
            f"{metric['business_success_rate']:.1%} | "
            f"{metric['confirmation_gate_success_rate']:.1%} | "
            f"{metric['confirmed_outcome_success_rate']:.1%} | "
            f"{metric['exact_match_rate']:.1%} | "
            f"{metric['average_step_count']:.2f} | "
            f"{_format_cost(metric.get('total_cost'))} |"
        )
    gaps = [
        scenario
        for scenario in scenario_metrics
        if (scenario_metrics.get(scenario) or {}).get(
            "confirmed_outcome_success_rate", 0.0
        )
        < 1.0
    ]
    lines.extend(
        [
            "",
            "## 当前能力缺口",
            "",
            f"- {', '.join(gaps) if gaps else 'none'}",
            "",
            "Cost is recorded only when verifiable provider usage is available; rule runs are `0`.",
        ]
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run representative Retail regression tasks.")
    parser.add_argument("--simulations-dir", required=True)
    parser.add_argument("--planner-type", choices=["rule", "llm"], default="rule")
    parser.add_argument("--run-name")
    parser.add_argument("--report-path", type=Path)
    args = parser.parse_args(argv)
    artifact_path = run_runtime_regression(
        simulations_dir=Path(args.simulations_dir),
        planner_type=args.planner_type,
        run_name=args.run_name,
        report_path=args.report_path,
    )
    print(f"runtime_regression_artifact={artifact_path}")
    if args.report_path:
        print(f"runtime_regression_report={args.report_path}")
    return 0


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _format_cost(value: object) -> str:
    return "N/A" if value is None else f"{float(value):.6f}"


def _format_cny(value: object) -> str:
    return "N/A" if value is None else f"CNY {float(value):.6f}"


if __name__ == "__main__":
    raise SystemExit(main())
