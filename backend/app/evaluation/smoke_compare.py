from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel


SmokeDiffStatus = Literal["regression", "improvement", "unchanged", "added", "removed"]


class SmokeTaskDiff(BaseModel):
    task_id: str
    status: SmokeDiffStatus
    baseline_exact_match: bool | None
    candidate_exact_match: bool | None
    baseline_business_success: bool | None = None
    candidate_business_success: bool | None = None
    baseline_stopped_reason: str | None
    candidate_stopped_reason: str | None
    baseline_failure_category: str | None
    candidate_failure_category: str | None


class SmokeComparison(BaseModel):
    baseline_run: str
    candidate_run: str
    task_diffs: list[SmokeTaskDiff]
    regression_count: int
    improvement_count: int
    unchanged_count: int


def compare_smoke_runs(
    simulations_dir: Path,
    *,
    baseline_run: str,
    candidate_run: str,
) -> SmokeComparison:
    if not _is_smoke_run(baseline_run) or not _is_smoke_run(candidate_run):
        raise KeyError("Smoke comparison requires two smoke-* runs.")
    baseline = _load_results(simulations_dir, baseline_run)
    candidate = _load_results(simulations_dir, candidate_run)
    task_ids = sorted(set(baseline) | set(candidate), key=_task_sort_key)
    task_diffs = [
        _compare_task(task_id, baseline.get(task_id), candidate.get(task_id))
        for task_id in task_ids
    ]
    return SmokeComparison(
        baseline_run=baseline_run,
        candidate_run=candidate_run,
        task_diffs=task_diffs,
        regression_count=sum(1 for diff in task_diffs if diff.status == "regression"),
        improvement_count=sum(1 for diff in task_diffs if diff.status == "improvement"),
        unchanged_count=sum(1 for diff in task_diffs if diff.status == "unchanged"),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare two saved smoke artifacts.")
    parser.add_argument("--simulations-dir", required=True)
    parser.add_argument("--baseline-run", required=True)
    parser.add_argument("--candidate-run", required=True)
    args = parser.parse_args(argv)
    comparison = compare_smoke_runs(
        Path(args.simulations_dir),
        baseline_run=args.baseline_run,
        candidate_run=args.candidate_run,
    )
    print(
        f"baseline={comparison.baseline_run} candidate={comparison.candidate_run} "
        f"regressions={comparison.regression_count} improvements={comparison.improvement_count} "
        f"unchanged={comparison.unchanged_count}"
    )
    for diff in comparison.task_diffs:
        print(
            f"task {diff.task_id}: {diff.status} "
            f"{diff.baseline_failure_category or '-'} -> {diff.candidate_failure_category or '-'}"
        )
    return 0


def _load_results(simulations_dir: Path, run_name: str) -> dict[str, dict]:
    artifact = simulations_dir / run_name / "runtime_subset.json"
    if not artifact.exists():
        raise KeyError(f"Smoke artifact not found: {run_name}")
    payload = json.loads(artifact.read_text())
    return {str(result.get("task_id")): result for result in payload.get("results", [])}


def _compare_task(task_id: str, baseline: dict | None, candidate: dict | None) -> SmokeTaskDiff:
    baseline_exact = _exact_match(baseline)
    candidate_exact = _exact_match(candidate)
    baseline_business = _business_success(baseline)
    candidate_business = _business_success(candidate)
    return SmokeTaskDiff(
        task_id=task_id,
        status=_diff_status(baseline_business, candidate_business),
        baseline_exact_match=baseline_exact,
        candidate_exact_match=candidate_exact,
        baseline_business_success=baseline_business,
        candidate_business_success=candidate_business,
        baseline_stopped_reason=_stopped_reason(baseline),
        candidate_stopped_reason=_stopped_reason(candidate),
        baseline_failure_category=_failure_category(baseline),
        candidate_failure_category=_failure_category(candidate),
    )


def _diff_status(
    baseline_exact: bool | None,
    candidate_exact: bool | None,
) -> SmokeDiffStatus:
    if baseline_exact is None:
        return "added"
    if candidate_exact is None:
        return "removed"
    if baseline_exact and not candidate_exact:
        return "regression"
    if not baseline_exact and candidate_exact:
        return "improvement"
    return "unchanged"


def _exact_match(result: dict | None) -> bool | None:
    if result is None:
        return None
    return bool(result.get("check", {}).get("exact_match"))


def _business_success(result: dict | None) -> bool | None:
    if result is None:
        return None
    check = result.get("check", {})
    if "business_success" in check:
        return bool(check.get("business_success"))
    return bool(check.get("exact_match"))


def _stopped_reason(result: dict | None) -> str | None:
    if result is None:
        return None
    return result.get("stopped_reason")


def _failure_category(result: dict | None) -> str | None:
    if result is None:
        return None
    category = result.get("failure_summary", {}).get("category")
    return str(category) if category else None


def _is_smoke_run(run_name: str) -> bool:
    return run_name.startswith("smoke-")


def _task_sort_key(task_id: str) -> tuple[int, str]:
    return (0, f"{int(task_id):08d}") if task_id.isdigit() else (1, task_id)


if __name__ == "__main__":
    raise SystemExit(main())
