import json

from app.evaluation.runtime_quality_gate import check_runtime_quality_gate


def test_quality_gate_accepts_complete_outcomes_within_cost_budget(tmp_path):
    artifact = tmp_path / "runtime_subset.json"
    artifact.write_text(
        json.dumps(
            {
                "planner_type": "llm",
                "summary": {
                    "total_tasks": 5,
                    "confirmed_outcome_success_count": 5,
                    "average_estimated_list_cost_cny": 0.011,
                },
                "results": [
                    {
                        "outcome_verification_mode": "confirmed_state",
                        "check": {"confirmed_outcome_success": True},
                    }
                    for _ in range(5)
                ],
            }
        )
    )

    result = check_runtime_quality_gate(
        artifact,
        required_confirmed_outcomes=5,
        max_average_estimated_cost_cny=0.02,
        expected_planner_type="llm",
    )

    assert result.confirmed_outcomes == 5
    assert result.passed is True


def test_quality_gate_rejects_missing_outcome_or_excess_cost(tmp_path):
    artifact = tmp_path / "runtime_subset.json"
    artifact.write_text(
        json.dumps(
            {
                "planner_type": "llm",
                "summary": {
                    "total_tasks": 5,
                    "confirmed_outcome_success_count": 4,
                    "average_estimated_list_cost_cny": 0.03,
                },
                "results": [
                    {
                        "outcome_verification_mode": "confirmed_state",
                        "check": {"confirmed_outcome_success": index < 4},
                    }
                    for index in range(5)
                ],
            }
        )
    )

    result = check_runtime_quality_gate(
        artifact,
        required_confirmed_outcomes=5,
        max_average_estimated_cost_cny=0.02,
        expected_planner_type="llm",
    )

    assert result.passed is False
    assert "confirmed outcomes 4/5" in result.failures
    assert "average estimated list cost CNY 0.030000 exceeds 0.020000" in result.failures


def test_quality_gate_requires_cost_when_budget_is_configured(tmp_path):
    artifact = tmp_path / "runtime_subset.json"
    artifact.write_text(
        json.dumps(
            {
                "planner_type": "llm",
                "summary": {"total_tasks": 5, "confirmed_outcome_success_count": 5},
                "results": [
                    {
                        "outcome_verification_mode": "confirmed_state",
                        "check": {"confirmed_outcome_success": True},
                    }
                    for _ in range(5)
                ],
            }
        )
    )

    result = check_runtime_quality_gate(
        artifact,
        required_confirmed_outcomes=5,
        max_average_estimated_cost_cny=0.02,
        expected_planner_type="llm",
    )

    assert result.passed is False
    assert "estimated list cost unavailable" in result.failures


def test_quality_gate_recomputes_results_and_rejects_wrong_planner(tmp_path):
    artifact = tmp_path / "runtime_subset.json"
    artifact.write_text(
        json.dumps(
            {
                "planner_type": "rule",
                "summary": {"total_tasks": 5, "confirmed_outcome_success_count": 5},
                "results": [
                    {
                        "outcome_verification_mode": "confirmation_gate",
                        "check": {"confirmed_outcome_success": True},
                    }
                    for _ in range(4)
                ],
            }
        )
    )

    result = check_runtime_quality_gate(
        artifact,
        required_confirmed_outcomes=5,
        expected_planner_type="llm",
    )

    assert result.passed is False
    assert "planner type rule does not match llm" in result.failures
    assert "artifact results 4 does not match total tasks 5" in result.failures
    assert "confirmed outcomes 0/5" in result.failures


def test_quality_gate_rejects_artifact_smaller_than_required_total(tmp_path):
    artifact = tmp_path / "runtime_subset.json"
    artifact.write_text(
        json.dumps(
            {
                "planner_type": "rule",
                "summary": {"total_tasks": 1},
                "results": [
                    {
                        "outcome_verification_mode": "confirmed_state",
                        "check": {"confirmed_outcome_success": True},
                    }
                ],
            }
        )
    )

    result = check_runtime_quality_gate(
        artifact,
        required_confirmed_outcomes=1,
        required_total_tasks=9,
    )

    assert result.passed is False
    assert "total tasks 1/9" in result.failures


def test_quality_gate_rejects_failed_order_lookups_above_limit(tmp_path):
    artifact = tmp_path / "runtime_subset.json"
    artifact.write_text(
        json.dumps(
            {
                "planner_type": "llm",
                "summary": {"total_tasks": 1},
                "results": [
                    {
                        "outcome_verification_mode": "confirmed_state",
                        "check": {"confirmed_outcome_success": True},
                        "trace_entries": [
                            {
                                "kind": "tool",
                                "tool_name": "get_order_details",
                                "content": "Order not found",
                            },
                            {
                                "kind": "tool",
                                "tool_name": "get_product_details",
                                "content": "Product not found",
                            },
                        ],
                    }
                ],
            }
        )
    )

    result = check_runtime_quality_gate(
        artifact,
        required_confirmed_outcomes=1,
        max_failed_order_lookups=0,
        expected_planner_type="llm",
    )

    assert result.failed_order_lookups == 1
    assert result.passed is False
    assert "failed order lookups 1 exceeds 0" in result.failures
