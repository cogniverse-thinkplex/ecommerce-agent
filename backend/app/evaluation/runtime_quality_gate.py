from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import BaseModel, Field


class RuntimeQualityGateResult(BaseModel):
    passed: bool
    confirmed_outcomes: int
    total_tasks: int
    failed_order_lookups: int = 0
    average_estimated_list_cost_cny: float | None = None
    failures: list[str] = Field(default_factory=list)


def check_runtime_quality_gate(
    artifact_path: Path,
    *,
    required_confirmed_outcomes: int,
    required_total_tasks: int | None = None,
    max_average_estimated_cost_cny: float | None = None,
    max_failed_order_lookups: int | None = None,
    expected_planner_type: str | None = None,
) -> RuntimeQualityGateResult:
    artifact = json.loads(artifact_path.read_text())
    summary = artifact.get("summary") or {}
    total_tasks = int(summary.get("total_tasks") or 0)
    results = artifact.get("results") or []
    confirmed_outcomes = sum(
        bool((result.get("check") or {}).get("confirmed_outcome_success"))
        and result.get("outcome_verification_mode") == "confirmed_state"
        for result in results
        if isinstance(result, dict)
    )
    failed_order_lookups = sum(
        entry.get("tool_name") == "get_order_details"
        and "Order not found" in str(entry.get("content") or "")
        for result in results
        if isinstance(result, dict)
        for entry in result.get("trace_entries") or []
        if isinstance(entry, dict)
    )
    estimated_cost = summary.get("average_estimated_list_cost_cny")
    average_estimated_cost = (
        float(estimated_cost) if estimated_cost is not None else None
    )
    failures: list[str] = []
    planner_type = str(artifact.get("planner_type") or "")
    if expected_planner_type is not None and planner_type != expected_planner_type:
        failures.append(
            f"planner type {planner_type or 'missing'} does not match {expected_planner_type}"
        )
    if len(results) != total_tasks:
        failures.append(
            f"artifact results {len(results)} does not match total tasks {total_tasks}"
        )
    if required_total_tasks is not None and total_tasks < required_total_tasks:
        failures.append(f"total tasks {total_tasks}/{required_total_tasks}")
    if confirmed_outcomes < required_confirmed_outcomes:
        failures.append(
            f"confirmed outcomes {confirmed_outcomes}/{required_confirmed_outcomes}"
        )
    if max_average_estimated_cost_cny is not None:
        if average_estimated_cost is None:
            failures.append("estimated list cost unavailable")
        elif average_estimated_cost > max_average_estimated_cost_cny:
            failures.append(
                "average estimated list cost CNY "
                f"{average_estimated_cost:.6f} exceeds "
                f"{max_average_estimated_cost_cny:.6f}"
            )
    if (
        max_failed_order_lookups is not None
        and failed_order_lookups > max_failed_order_lookups
    ):
        failures.append(
            f"failed order lookups {failed_order_lookups} exceeds "
            f"{max_failed_order_lookups}"
        )
    return RuntimeQualityGateResult(
        passed=not failures,
        confirmed_outcomes=confirmed_outcomes,
        total_tasks=total_tasks,
        failed_order_lookups=failed_order_lookups,
        average_estimated_list_cost_cny=average_estimated_cost,
        failures=failures,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check a runtime regression artifact.")
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--required-confirmed-outcomes", type=int, default=5)
    parser.add_argument("--required-total-tasks", type=int)
    parser.add_argument("--max-average-estimated-cost-cny", type=float)
    parser.add_argument("--max-failed-order-lookups", type=int)
    parser.add_argument("--expected-planner-type", choices=["rule", "llm"])
    args = parser.parse_args(argv)
    result = check_runtime_quality_gate(
        args.artifact,
        required_confirmed_outcomes=args.required_confirmed_outcomes,
        required_total_tasks=args.required_total_tasks,
        max_average_estimated_cost_cny=args.max_average_estimated_cost_cny,
        max_failed_order_lookups=args.max_failed_order_lookups,
        expected_planner_type=args.expected_planner_type,
    )
    print(result.model_dump_json())
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
