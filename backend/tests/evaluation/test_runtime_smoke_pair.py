from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.evaluation.smoke_compare import compare_smoke_runs


def _write_artifact(path: Path, *, run_name: str, planner_type: str, exact_match: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "run_name": run_name,
                "planner_type": planner_type,
                "task_ids": ["0"],
                "summary": {"total_tasks": 1, "exact_match_count": 1 if exact_match else 0},
                "results": [
                    {
                        "task_id": "0",
                        "check": {"exact_match": exact_match},
                        "stopped_reason": "ok" if exact_match else "no_proposal",
                        "failure_summary": {}
                        if exact_match
                        else {"category": "planner_terminal"},
                    }
                ],
            }
        )
    )


def test_run_runtime_smoke_pair_archives_rule_llm_runs_and_diff_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from app.evaluation import runtime_smoke_pair

    simulations_dir = tmp_path / "simulations"
    report_dir = tmp_path / "docs" / "smoke"
    calls: list[dict] = []

    def fake_run_runtime_smoke(**kwargs):
        calls.append(kwargs)
        run_name = kwargs["run_name"]
        artifact_path = simulations_dir / run_name / "runtime_subset.json"
        _write_artifact(
            artifact_path,
            run_name=run_name,
            planner_type=kwargs["planner_type"],
            exact_match=kwargs["planner_type"] == "rule",
        )
        return artifact_path

    monkeypatch.setattr(runtime_smoke_pair, "run_runtime_smoke", fake_run_runtime_smoke)

    result = runtime_smoke_pair.run_runtime_smoke_pair(
        simulations_dir=simulations_dir,
        report_dir=report_dir,
        max_steps=4,
        timestamp="20261013T120000Z",
    )

    assert [call["planner_type"] for call in calls] == ["rule", "llm"]
    assert calls[0]["run_name"] == "smoke-rule-20261013T120000Z"
    assert calls[1]["run_name"] == "smoke-llm-20261013T120000Z"
    assert all(call["max_steps"] == 4 for call in calls)
    assert result.rule_run == "smoke-rule-20261013T120000Z"
    assert result.llm_run == "smoke-llm-20261013T120000Z"
    assert result.report_path == report_dir / "smoke-pair-20261013T120000Z.md"
    assert result.comparison.regression_count == 1

    report = result.report_path.read_text()
    assert "# Runtime Smoke Report: smoke-llm-20261013T120000Z" in report
    assert "- Baseline: `smoke-rule-20261013T120000Z`" in report
    assert "- Candidate: `smoke-llm-20261013T120000Z`" in report
    assert "| 0 | regression | true | false | - | planner_terminal |" in report
    assert "检查 planner 终止原因" in report


def test_runtime_smoke_pair_cli_prints_artifact_and_report_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    from app.evaluation import runtime_smoke_pair

    simulations_dir = tmp_path / "simulations"
    report_dir = tmp_path / "reports"

    def fake_run_runtime_smoke(**kwargs):
        artifact_path = simulations_dir / kwargs["run_name"] / "runtime_subset.json"
        _write_artifact(
            artifact_path,
            run_name=kwargs["run_name"],
            planner_type=kwargs["planner_type"],
            exact_match=True,
        )
        return artifact_path

    monkeypatch.setattr(runtime_smoke_pair, "run_runtime_smoke", fake_run_runtime_smoke)

    exit_code = runtime_smoke_pair.main(
        [
            "--simulations-dir",
            str(simulations_dir),
            "--report-dir",
            str(report_dir),
            "--timestamp",
            "20261013T120000Z",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "rule_smoke_artifact=" in output
    assert "llm_smoke_artifact=" in output
    assert f"smoke_pair_report={report_dir / 'smoke-pair-20261013T120000Z.md'}" in output
    assert "smoke_pair_regressions=0" in output


def test_compare_smoke_runs_observes_pair_artifacts(tmp_path: Path):
    simulations_dir = tmp_path / "simulations"
    _write_artifact(
        simulations_dir / "smoke-rule-demo" / "runtime_subset.json",
        run_name="smoke-rule-demo",
        planner_type="rule",
        exact_match=False,
    )
    _write_artifact(
        simulations_dir / "smoke-llm-demo" / "runtime_subset.json",
        run_name="smoke-llm-demo",
        planner_type="llm",
        exact_match=True,
    )

    comparison = compare_smoke_runs(
        simulations_dir,
        baseline_run="smoke-rule-demo",
        candidate_run="smoke-llm-demo",
    )

    assert comparison.improvement_count == 1
    assert comparison.task_diffs[0].status == "improvement"
