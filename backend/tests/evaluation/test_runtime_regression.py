import json

from app.evaluation.runtime_regression import (
    REGRESSION_SCENARIOS,
    build_regression_markdown_report,
    run_runtime_regression,
)


def test_regression_manifest_covers_representative_write_scenarios():
    assert [scenario.scenario for scenario in REGRESSION_SCENARIOS] == [
        "exchange",
        "exchange",
        "return",
        "return",
        "cancel",
        "cancel",
        "address_update",
        "address_update",
        "payment_update",
    ]
    assert [scenario.task_id for scenario in REGRESSION_SCENARIOS] == [
        "0",
        "52",
        "2",
        "48",
        "38",
        "69",
        "17",
        "71",
        "40",
    ]
    assert next(
        scenario.step_budget
        for scenario in REGRESSION_SCENARIOS
        if scenario.task_id == "2"
    ) == 12


def test_rule_regression_persists_confirmed_outcomes_and_scenario_metrics(tmp_path):
    artifact_path = run_runtime_regression(
        simulations_dir=tmp_path,
        planner_type="rule",
        run_name="regression-rule-demo",
    )

    artifact = json.loads(artifact_path.read_text())

    assert artifact["task_scenarios"] == {
        "0": "exchange",
        "52": "exchange",
        "2": "return",
        "48": "return",
        "38": "cancel",
        "69": "cancel",
        "17": "address_update",
        "71": "address_update",
        "40": "payment_update",
    }
    assert artifact["summary"]["total_tasks"] == 9
    assert artifact["summary"]["business_success_count"] == 5
    assert artifact["summary"]["business_success_rate"] == 5 / 9
    assert artifact["summary"]["confirmation_gate_success_count"] == 5
    assert artifact["summary"]["confirmed_outcome_success_count"] == 5
    assert artifact["summary"]["average_step_count"] > 0
    assert artifact["summary"]["total_cost"] == 0.0
    exchange = artifact["summary"]["scenario_metrics"]["exchange"]
    assert exchange["task_count"] == 2
    assert exchange["confirmed_outcome_success_rate"] == 0.5
    assert exchange["cost_available"] is True
    assert artifact["summary"]["scenario_metrics"]["cancel"][
        "business_success_rate"
    ] == 0.5
    task_zero = next(result for result in artifact["results"] if result["task_id"] == "0")
    assert task_zero["check"]["outcome"]["status"] == "confirmed_state_verified"
    assert task_zero["check"]["business_success_basis"] == "confirmed_state_change"


def test_regression_markdown_report_exposes_capability_gaps(tmp_path):
    artifact_path = run_runtime_regression(
        simulations_dir=tmp_path,
        planner_type="rule",
        run_name="regression-rule-report",
    )

    report = build_regression_markdown_report(json.loads(artifact_path.read_text()))

    assert "# Runtime Regression Report: regression-rule-report" in report
    assert "- Business success: `5/9`" in report
    assert "- Confirmation gate success: `5/9`" in report
    assert "- Confirmed outcome success: `5/9`" in report
    assert "- Tokens: `0 input / 0 output / 0 total`" in report
    assert "- Estimated list cost: `N/A`" in report
    assert "| exchange | 2 | 50.0% | 50.0% | 50.0% | 50.0% | 2.50 | 0.000000 |" in report
    assert "| cancel | 2 | 50.0%" in report
    assert report.count("| exchange |") == 1
    assert report.count("| return |") == 1
    assert "当前能力缺口" in report
    assert "exchange, return, cancel, address_update" in report


def test_regression_markdown_report_includes_dynamic_multi_write_scenario():
    report = build_regression_markdown_report(
        {
            "run_name": "multi-write",
            "planner_type": "llm",
            "summary": {
                "total_tasks": 1,
                "scenario_metrics": {
                    "multi_write": {
                        "task_count": 1,
                        "business_success_rate": 0.0,
                        "confirmation_gate_success_rate": 0.0,
                        "confirmed_outcome_success_rate": 0.0,
                        "exact_match_rate": 0.0,
                        "average_step_count": 11.0,
                        "total_cost": None,
                    }
                },
            },
        }
    )

    assert "| multi_write | 1 | 0.0%" in report
    assert "- multi_write" in report
