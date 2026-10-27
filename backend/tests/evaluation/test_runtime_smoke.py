import json
from pathlib import Path

from app.evaluation.runtime_smoke import (
    SMOKE_TASK_STEP_BUDGETS,
    SMOKE_TASK_IDS,
    build_smoke_markdown_report,
    candidate_improvement_suggestions,
    run_runtime_smoke,
)
from app.evaluation.smoke_compare import SmokeComparison, SmokeTaskDiff


def test_build_smoke_markdown_report_summarizes_artifact_and_comparison():
    artifact = {
        "run_name": "smoke-rule-demo",
        "planner_type": "rule",
        "task_ids": ["0", "1"],
        "summary": {
            "total_tasks": 2,
            "exact_match_count": 1,
            "business_success_count": 2,
            "stopped_reasons": {"pending_confirmation": 1, "no_proposal": 1},
        },
        "results": [
            {"failure_summary": {"category": "pending_confirmation"}},
            {"failure_summary": {"category": "action_deviation"}},
        ],
    }
    comparison = SmokeComparison(
        baseline_run="smoke-rule-old",
        candidate_run="smoke-rule-demo",
        task_diffs=[
            SmokeTaskDiff(
                task_id="1",
                status="regression",
                baseline_exact_match=True,
                candidate_exact_match=False,
                baseline_business_success=False,
                candidate_business_success=False,
                baseline_stopped_reason="pending_confirmation",
                candidate_stopped_reason="no_proposal",
                baseline_failure_category="pending_confirmation",
                candidate_failure_category="action_deviation",
            )
        ],
        regression_count=1,
        improvement_count=0,
        unchanged_count=0,
    )

    report = build_smoke_markdown_report(artifact, comparison=comparison)

    assert "# Runtime Smoke Report: smoke-rule-demo" in report
    assert "- Planner: `rule`" in report
    assert "- Exact match: `1/2`" in report
    assert "- Business success: `2/2`" in report
    assert "- `action_deviation`: 1" in report
    assert "## Smoke Diff" in report
    assert "| Task | Status | Baseline business | Candidate business |" in report
    assert "| 1 | regression | false | false | pending_confirmation | action_deviation |" in report
    assert "优先检查发生动作偏差的 task" in report


def test_candidate_improvement_suggestions_maps_failure_categories():
    suggestions = candidate_improvement_suggestions(
        {"action_deviation": 2, "planner_terminal": 1}
    )

    assert any("动作偏差" in suggestion for suggestion in suggestions)
    assert any("planner 终止" in suggestion for suggestion in suggestions)


def test_candidate_improvement_suggestions_treats_business_success_as_non_failure():
    suggestions = candidate_improvement_suggestions(
        {"business_success": 1, "pending_confirmation": 2}
    )

    assert suggestions == ["业务目标均已完成；可继续审计严格动作轨迹差异。"]


def test_smoke_task_ids_are_fixed_minimal_regression_set():
    assert SMOKE_TASK_IDS == ["0", "1", "2"]
    assert SMOKE_TASK_STEP_BUDGETS == {"2": 10}


def test_rule_smoke_uses_longer_budget_for_return_task(tmp_path):
    artifact_path = run_runtime_smoke(
        simulations_dir=tmp_path,
        planner_type="rule",
        max_steps=6,
        run_name="smoke-rule-budget-demo",
    )

    artifact = json.loads(artifact_path.read_text())
    task_two = next(result for result in artifact["results"] if result["task_id"] == "2")
    assert artifact["task_step_budgets"] == {"2": 10}
    assert task_two["step_budget"] == 10
    assert task_two["check"]["business_success"] is True
    assert task_two["stopped_reason"] == "pending_confirmation"
    assert task_two["failure_summary"]["category"] == "confirmation_gate_success"
