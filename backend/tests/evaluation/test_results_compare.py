import json

from app.evaluation.results_compare import compare_evaluation_runs


def test_compare_evaluation_runs_summarizes_runs_with_results(tmp_path):
    _write_results(
        tmp_path / "run-a" / "results.json",
        [
            {"task_id": "0", "agent_cost": 0.1, "user_cost": 0.05, "reward": 1.0},
            {"task_id": "1", "agent_cost": 0.2, "user_cost": 0.05, "reward": 0.0},
        ],
    )
    _write_results(
        tmp_path / "run-b" / "results.json",
        [
            {"task_id": "2", "agent_cost": 0.3, "user_cost": 0.1, "reward": 1.0},
        ],
    )
    (tmp_path / "pending-run").mkdir()

    comparison = compare_evaluation_runs(tmp_path)

    assert [run.run_name for run in comparison.runs] == ["run-a", "run-b"]
    assert comparison.runs[0].simulations == 2
    assert comparison.runs[0].run_type == "tau2"
    assert comparison.runs[0].average_reward == 0.5
    assert comparison.runs[0].total_cost == 0.4
    assert comparison.runs[0].average_cost == 0.2
    assert comparison.runs[1].simulations == 1
    assert comparison.runs[1].average_reward == 1.0
    assert comparison.runs[1].total_cost == 0.4


def test_compare_evaluation_runs_includes_runtime_subset_artifacts(tmp_path):
    run_dir = tmp_path / "runtime-run"
    run_dir.mkdir()
    (run_dir / "runtime_subset.json").write_text(
        json.dumps(
            {
                "run_name": "runtime-run",
                "created_at": "2026-09-21T00:00:00Z",
                "task_ids": ["0"],
                "max_steps": 6,
                "results": [
                    {
                        "task_id": "0",
                        "conversation_id": "retail-task-0",
                        "stopped_reason": "pending_confirmation",
                        "check": {
                            "task_id": "0",
                            "expected_actions": ["a"],
                            "actual_actions": ["a"],
                            "matched_prefix_count": 1,
                            "exact_match": True,
                            "business_success": True,
                            "missing_actions": [],
                            "unexpected_actions": [],
                        },
                        "diagnostic": {
                            "first_mismatch_index": None,
                            "expected_action": None,
                            "actual_action": None,
                            "message": "动作序列完全匹配。",
                        },
                    }
                ],
            }
        )
    )

    comparison = compare_evaluation_runs(tmp_path)

    assert len(comparison.runs) == 1
    assert comparison.runs[0].run_name == "runtime-run"
    assert comparison.runs[0].run_type == "runtime_subset"
    assert comparison.runs[0].run_group == "adhoc"
    assert comparison.runs[0].is_smoke is False
    assert comparison.runs[0].simulations == 1
    assert comparison.runs[0].average_reward == 1.0
    assert comparison.runs[0].exact_match_rate == 1.0
    assert comparison.runs[0].business_success_rate == 1.0


def test_compare_evaluation_runs_labels_smoke_artifacts(tmp_path):
    run_dir = tmp_path / "smoke-rule-20261002T150000Z"
    run_dir.mkdir()
    (run_dir / "runtime_subset.json").write_text(
        json.dumps(
            {
                "run_name": "smoke-rule-20261002T150000Z",
                "created_at": "2026-10-02T15:00:00Z",
                "task_ids": ["0"],
                "max_steps": 6,
                "results": [
                    {
                        "task_id": "0",
                        "conversation_id": "retail-task-0",
                        "stopped_reason": "pending_confirmation",
                        "check": {
                            "task_id": "0",
                            "expected_actions": ["a"],
                            "actual_actions": ["a"],
                            "matched_prefix_count": 1,
                            "exact_match": True,
                            "missing_actions": [],
                            "unexpected_actions": [],
                        },
                        "diagnostic": {
                            "first_mismatch_index": None,
                            "expected_action": None,
                            "actual_action": None,
                            "message": "动作序列完全匹配。",
                        },
                        "failure_summary": {
                            "category": "pending_confirmation",
                            "recommended_action": "confirm",
                        },
                    }
                ],
            }
        )
    )

    comparison = compare_evaluation_runs(tmp_path)

    assert comparison.runs[0].run_group == "smoke"
    assert comparison.runs[0].is_smoke is True
    assert comparison.runs[0].failure_categories == {"pending_confirmation": 1}


def test_compare_evaluation_runs_returns_empty_for_missing_directory(tmp_path):
    comparison = compare_evaluation_runs(tmp_path / "missing")

    assert comparison.runs == []


def _write_results(path, simulations):
    path.parent.mkdir()
    path.write_text(json.dumps({"simulations": simulations}))
