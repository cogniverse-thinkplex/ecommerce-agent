import json

from app.evaluation.results_summary import summarize_results_file, summarize_run_dir


def test_summarize_results_file_computes_reward_and_cost(tmp_path):
    results_file = tmp_path / "results.json"
    results_file.write_text(
        json.dumps(
            {
                "simulations": [
                    {
                        "task_id": "0",
                        "agent_cost": 0.2,
                        "user_cost": 0.05,
                        "reward_info": {"reward": 1.0},
                    },
                    {
                        "task_id": "1",
                        "agent_cost": 0.1,
                        "user_cost": 0.05,
                        "reward_info": {"reward": 0.0},
                    },
                ]
            }
        )
    )

    summary = summarize_results_file(results_file, run_name="demo-run")

    assert summary.run_name == "demo-run"
    assert summary.simulations == 2
    assert summary.rewards == [1.0, 0.0]
    assert summary.average_reward == 0.5
    assert summary.total_cost == 0.4
    assert summary.average_cost == 0.2
    assert summary.task_ids == ["0", "1"]
    assert summary.run_type == "tau2"


def test_summarize_results_file_handles_legacy_reward_field(tmp_path):
    results_file = tmp_path / "results.json"
    results_file.write_text(
        json.dumps(
            {
                "simulations": [
                    {
                        "task_id": "legacy",
                        "agent_cost": None,
                        "user_cost": None,
                        "reward": 1.0,
                    }
                ]
            }
        )
    )

    summary = summarize_results_file(results_file, run_name="legacy-run")

    assert summary.rewards == [1.0]
    assert summary.cost_available is False
    assert summary.total_cost is None
    assert summary.average_cost is None


def test_summarize_run_dir_computes_runtime_subset_summary(tmp_path):
    run_dir = tmp_path / "runtime-run"
    run_dir.mkdir()
    (run_dir / "runtime_subset.json").write_text(
        json.dumps(
            {
                "run_name": "runtime-run",
                "created_at": "2026-09-21T00:00:00Z",
                "task_ids": ["0", "1"],
                "max_steps": 6,
                "results": [
                    {
                        "task_id": "0",
                        "conversation_id": "retail-task-0",
                        "stopped_reason": "pending_confirmation",
                        "check": {
                            "task_id": "0",
                            "expected_actions": ["a", "b"],
                            "actual_actions": ["a", "b"],
                            "matched_prefix_count": 2,
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
                    },
                    {
                        "task_id": "1",
                        "conversation_id": "retail-task-1",
                        "stopped_reason": "no_proposal",
                        "check": {
                            "task_id": "1",
                            "expected_actions": ["a", "b"],
                            "actual_actions": ["a"],
                            "matched_prefix_count": 1,
                            "exact_match": False,
                            "business_success": True,
                            "missing_actions": ["b"],
                            "unexpected_actions": [],
                        },
                        "diagnostic": {
                            "first_mismatch_index": 1,
                            "expected_action": "b",
                            "actual_action": None,
                            "message": "第 2 个动作缺失，预期执行 b。",
                        },
                    },
                ],
            }
        )
    )

    summary = summarize_run_dir(run_dir)

    assert summary.run_name == "runtime-run"
    assert summary.run_type == "runtime_subset"
    assert summary.run_group == "adhoc"
    assert summary.is_smoke is False
    assert summary.simulations == 2
    assert summary.task_ids == ["0", "1"]
    assert summary.rewards == [1.0, 0.0]
    assert summary.average_reward == 0.5
    assert summary.cost_available is False
    assert summary.total_cost is None
    assert summary.average_cost is None
    assert summary.exact_match_rate == 0.5
    assert summary.business_success_rate == 1.0
    assert summary.average_matched_prefix_count == 1.5
    assert summary.failure_categories == {}


def test_summarize_run_dir_labels_smoke_and_failure_categories(tmp_path):
    run_dir = tmp_path / "smoke-llm-20261002T150000Z"
    run_dir.mkdir()
    (run_dir / "runtime_subset.json").write_text(
        json.dumps(
            {
                "run_name": "smoke-llm-20261002T150000Z",
                "created_at": "2026-10-02T15:00:00Z",
                "task_ids": ["0", "1"],
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
                    },
                    {
                        "task_id": "1",
                        "conversation_id": "retail-task-1",
                        "stopped_reason": "no_proposal",
                        "check": {
                            "task_id": "1",
                            "expected_actions": ["a"],
                            "actual_actions": [],
                            "matched_prefix_count": 0,
                            "exact_match": False,
                            "missing_actions": ["a"],
                            "unexpected_actions": [],
                        },
                        "diagnostic": {
                            "first_mismatch_index": 0,
                            "expected_action": "a",
                            "actual_action": None,
                            "message": "第 1 个动作缺失，预期执行 a。",
                        },
                        "failure_summary": {
                            "category": "action_deviation",
                            "recommended_action": "check planner",
                        },
                    },
                ],
            }
        )
    )

    summary = summarize_run_dir(run_dir)

    assert summary.run_group == "smoke"
    assert summary.is_smoke is True
    assert summary.failure_categories == {
        "pending_confirmation": 1,
        "action_deviation": 1,
    }


def test_summarize_runtime_regression_exposes_steps_cost_and_group(tmp_path):
    run_dir = tmp_path / "regression-rule-demo"
    run_dir.mkdir()
    (run_dir / "runtime_subset.json").write_text(
        json.dumps(
            {
                "run_name": "regression-rule-demo",
                "results": [
                    {
                        "task_id": "0",
                        "step_count": 5,
                        "cost": 0.25,
                        "check": {
                            "exact_match": True,
                            "business_success": True,
                            "matched_prefix_count": 5,
                        },
                    },
                    {
                        "task_id": "2",
                        "step_count": 9,
                        "cost": 0.75,
                        "check": {
                            "exact_match": False,
                            "business_success": True,
                            "matched_prefix_count": 1,
                        },
                    },
                ],
            }
        )
    )

    summary = summarize_run_dir(run_dir)

    assert summary.run_group == "regression"
    assert summary.average_step_count == 7.0
    assert summary.total_cost == 1.0
    assert summary.average_cost == 0.5


def test_summarize_runtime_subset_preserves_unknown_cost(tmp_path):
    run_dir = tmp_path / "regression-llm-demo"
    run_dir.mkdir()
    (run_dir / "runtime_subset.json").write_text(
        json.dumps(
            {
                "run_name": "regression-llm-demo",
                "results": [
                    {
                        "task_id": "0",
                        "step_count": 1,
                        "cost": None,
                        "check": {
                            "exact_match": False,
                            "business_success": False,
                            "matched_prefix_count": 0,
                        },
                    }
                ],
            }
        )
    )

    summary = summarize_run_dir(run_dir)

    assert summary.cost_available is False
    assert summary.total_cost is None
    assert summary.average_cost is None
