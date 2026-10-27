from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from app.evaluation.runtime_task_runner import (
    RuntimePlannerType,
    run_retail_task_subset,
    save_runtime_task_subset_artifact,
)
from app.evaluation.smoke_compare import SmokeComparison, compare_smoke_runs

SMOKE_TASK_IDS = ["0", "1", "2"]
SMOKE_TASK_STEP_BUDGETS = {"2": 10}


def run_runtime_smoke(
    *,
    simulations_dir: Path,
    planner_type: RuntimePlannerType = "rule",
    max_steps: int = 6,
    run_name: str | None = None,
    compare_against: str | None = None,
    report_path: Path | None = None,
) -> Path:
    resolved_run_name = run_name or f"smoke-{planner_type}-{_timestamp()}"
    results = run_retail_task_subset(
        SMOKE_TASK_IDS,
        max_steps=max_steps,
        task_step_budgets=SMOKE_TASK_STEP_BUDGETS,
        planner_type=planner_type,
    )
    artifact = save_runtime_task_subset_artifact(
        results,
        output_dir=simulations_dir,
        run_name=resolved_run_name,
        max_steps=max_steps,
        task_step_budgets=SMOKE_TASK_STEP_BUDGETS,
    )
    comparison = (
        compare_smoke_runs(
            simulations_dir,
            baseline_run=compare_against,
            candidate_run=artifact.run_name,
        )
        if compare_against
        else None
    )
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            build_smoke_markdown_report(
                json.loads(Path(artifact.path).read_text()),
                comparison=comparison,
            )
        )
    return Path(artifact.path)


def build_smoke_markdown_report(
    artifact: dict,
    *,
    comparison: SmokeComparison | None = None,
) -> str:
    run_name = str(artifact.get("run_name") or "unknown")
    planner_type = str(artifact.get("planner_type") or "unknown")
    summary = artifact.get("summary") or {}
    total_tasks = int(summary.get("total_tasks") or len(artifact.get("results") or []))
    exact_match_count = int(summary.get("exact_match_count") or 0)
    business_success_count = int(
        summary.get("business_success_count")
        if summary.get("business_success_count") is not None
        else sum(
            1
            for result in artifact.get("results") or []
            if result.get("check", {}).get(
                "business_success",
                result.get("check", {}).get("exact_match", False),
            )
        )
    )
    failure_categories = _failure_categories(artifact.get("results") or [])
    lines = [
        f"# Runtime Smoke Report: {run_name}",
        "",
        f"- Planner: `{planner_type}`",
        f"- Tasks: `{', '.join(str(task_id) for task_id in artifact.get('task_ids', []))}`",
        f"- Exact match: `{exact_match_count}/{total_tasks}`",
        f"- Business success: `{business_success_count}/{total_tasks}`",
        f"- Task step budgets: `{artifact.get('task_step_budgets') or {}}`",
        "",
        "## Failure Categories",
        "",
    ]
    if failure_categories:
        lines.extend(
            f"- `{category}`: {count}"
            for category, count in sorted(failure_categories.items())
        )
    else:
        lines.append("- none")
    if comparison is not None:
        lines.extend(
            [
                "",
                "## Smoke Diff",
                "",
                f"- Baseline: `{comparison.baseline_run}`",
                f"- Candidate: `{comparison.candidate_run}`",
                f"- Regressions: `{comparison.regression_count}`",
                f"- Improvements: `{comparison.improvement_count}`",
                "",
                "| Task | Status | Baseline business | Candidate business | Baseline failure | Candidate failure |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        lines.extend(
            (
                f"| {diff.task_id} | {diff.status} | "
                f"{str(diff.baseline_business_success).lower()} | "
                f"{str(diff.candidate_business_success).lower()} | "
                f"{diff.baseline_failure_category or '-'} | "
                f"{diff.candidate_failure_category or '-'} |"
            )
            for diff in comparison.task_diffs
        )
    suggestions = candidate_improvement_suggestions(failure_categories)
    lines.extend(["", "## Candidate Improvement Suggestions", ""])
    lines.extend(f"- {suggestion}" for suggestion in suggestions)
    return "\n".join(lines) + "\n"


def candidate_improvement_suggestions(failure_categories: dict[str, int]) -> list[str]:
    suggestions: list[str] = []
    if failure_categories.get("action_deviation"):
        suggestions.append(
            "优先检查发生动作偏差的 task，对照 expected actions、skill routing 和 planner tool selection。"
        )
    if failure_categories.get("planner_terminal"):
        suggestions.append("检查 planner 终止原因，确认是否过早 final_response、need_more_info 或 invalid_output。")
    if failure_categories.get("rejected"):
        suggestions.append("检查 runtime rejection 事件，优先核对 tool schema、skill policy 和写操作 guard。")
    if failure_categories.get("max_steps"):
        suggestions.append("检查是否存在循环或缺少终止条件，必要时提高 max_steps 后复测。")
    if not suggestions:
        non_failure_categories = {
            "business_success",
            "confirmation_gate_success",
            "pending_confirmation",
            "success",
        }
        if failure_categories and set(failure_categories) <= non_failure_categories:
            suggestions.append("业务目标均已完成；可继续审计严格动作轨迹差异。")
        else:
            suggestions.append("暂无明确失败聚类，优先查看失败原因矩阵和 trace。")
    return suggestions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the fixed runtime smoke set.")
    parser.add_argument("--simulations-dir", required=True)
    parser.add_argument("--planner-type", choices=["rule", "llm"], default="rule")
    parser.add_argument("--max-steps", type=int, default=6)
    parser.add_argument("--run-name")
    parser.add_argument("--compare-against")
    parser.add_argument("--report-path", type=Path)
    args = parser.parse_args(argv)
    artifact_path = run_runtime_smoke(
        simulations_dir=Path(args.simulations_dir),
        planner_type=args.planner_type,
        max_steps=args.max_steps,
        run_name=args.run_name,
        compare_against=args.compare_against,
        report_path=args.report_path,
    )
    print(f"runtime_smoke_artifact={artifact_path}")
    if args.report_path:
        print(f"smoke_markdown_report={args.report_path}")
    return 0


def _failure_categories(results: list[dict]) -> dict[str, int]:
    categories: dict[str, int] = {}
    for result in results:
        category = result.get("failure_summary", {}).get("category")
        if category:
            categories[str(category)] = categories.get(str(category), 0) + 1
    return categories


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


if __name__ == "__main__":
    raise SystemExit(main())
