import json

import pytest

from app.evaluation.smoke_compare import compare_smoke_runs


def test_compare_smoke_runs_reports_regression_and_improvement(tmp_path):
    _write_runtime_subset(
        tmp_path / "smoke-rule-old" / "runtime_subset.json",
        [
            _result("0", exact_match=True, category="pending_confirmation"),
            _result("1", exact_match=False, category="action_deviation"),
        ],
    )
    _write_runtime_subset(
        tmp_path / "smoke-rule-new" / "runtime_subset.json",
        [
            _result("0", exact_match=False, category="action_deviation"),
            _result("1", exact_match=True, category="pending_confirmation"),
        ],
    )

    comparison = compare_smoke_runs(
        tmp_path,
        baseline_run="smoke-rule-old",
        candidate_run="smoke-rule-new",
    )

    assert comparison.baseline_run == "smoke-rule-old"
    assert comparison.candidate_run == "smoke-rule-new"
    assert comparison.regression_count == 1
    assert comparison.improvement_count == 1
    assert [(item.task_id, item.status) for item in comparison.task_diffs] == [
        ("0", "regression"),
        ("1", "improvement"),
    ]
    assert comparison.task_diffs[0].baseline_failure_category == "pending_confirmation"
    assert comparison.task_diffs[0].candidate_failure_category == "action_deviation"


def test_compare_smoke_runs_rejects_non_smoke_names(tmp_path):
    with pytest.raises(KeyError):
        compare_smoke_runs(tmp_path, baseline_run="runtime-run", candidate_run="smoke-new")


def test_compare_smoke_runs_uses_business_success_for_regression_status(tmp_path):
    baseline = _result("2", exact_match=False, category="action_deviation")
    baseline["check"]["business_success"] = True
    candidate = _result("2", exact_match=False, category="action_deviation")
    candidate["check"]["business_success"] = False
    _write_runtime_subset(
        tmp_path / "smoke-rule-business" / "runtime_subset.json",
        [baseline],
    )
    _write_runtime_subset(
        tmp_path / "smoke-llm-business" / "runtime_subset.json",
        [candidate],
    )

    comparison = compare_smoke_runs(
        tmp_path,
        baseline_run="smoke-rule-business",
        candidate_run="smoke-llm-business",
    )

    diff = comparison.task_diffs[0]
    assert diff.status == "regression"
    assert diff.baseline_exact_match is False
    assert diff.candidate_exact_match is False
    assert diff.baseline_business_success is True
    assert diff.candidate_business_success is False


def _write_runtime_subset(path, results):
    path.parent.mkdir()
    path.write_text(
        json.dumps(
            {
                "run_name": path.parent.name,
                "created_at": "2026-10-03T00:00:00Z",
                "task_ids": [result["task_id"] for result in results],
                "max_steps": 6,
                "results": results,
            }
        )
    )


def _result(task_id, *, exact_match, category):
    actual_actions = ["a"] if exact_match else []
    return {
        "task_id": task_id,
        "conversation_id": f"retail-task-{task_id}",
        "stopped_reason": "pending_confirmation" if exact_match else "no_proposal",
        "check": {
            "task_id": task_id,
            "expected_actions": ["a"],
            "actual_actions": actual_actions,
            "matched_prefix_count": len(actual_actions),
            "exact_match": exact_match,
            "missing_actions": [] if exact_match else ["a"],
            "unexpected_actions": [],
        },
        "diagnostic": {
            "first_mismatch_index": None if exact_match else 0,
            "expected_action": None if exact_match else "a",
            "actual_action": None,
            "message": "动作序列完全匹配。" if exact_match else "第 1 个动作缺失，预期执行 a。",
        },
        "failure_summary": {
            "category": category,
            "recommended_action": "check",
        },
    }
