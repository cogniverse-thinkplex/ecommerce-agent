import json

from app.evaluation.results_index import list_evaluation_runs


def test_list_evaluation_runs_reports_result_availability(tmp_path):
    completed_run = tmp_path / "completed-run"
    completed_run.mkdir()
    (completed_run / "results.json").write_text(
        json.dumps({"simulations": [{"task_id": "0"}]})
    )
    pending_run = tmp_path / "pending-run"
    pending_run.mkdir()
    (tmp_path / "notes.txt").write_text("not a run")

    runs = list_evaluation_runs(tmp_path)

    assert [run.run_name for run in runs] == ["completed-run", "pending-run"]
    assert runs[0].has_results is True
    assert runs[0].run_type == "tau2"
    assert runs[0].summary_url == "/evaluations/completed-run/summary"
    assert runs[0].updated_at is not None
    assert runs[1].has_results is False
    assert runs[1].run_type == "unknown"
    assert runs[1].summary_url is None


def test_list_evaluation_runs_reports_runtime_subset_artifacts(tmp_path):
    runtime_run = tmp_path / "runtime-run"
    runtime_run.mkdir()
    (runtime_run / "runtime_subset.json").write_text(
        json.dumps(
            {
                "run_name": "runtime-run",
                "created_at": "2026-09-21T00:00:00Z",
                "task_ids": ["0"],
                "max_steps": 6,
                "results": [],
            }
        )
    )

    runs = list_evaluation_runs(tmp_path)

    assert len(runs) == 1
    assert runs[0].run_name == "runtime-run"
    assert runs[0].has_results is True
    assert runs[0].run_type == "runtime_subset"
    assert runs[0].run_group == "adhoc"
    assert runs[0].is_smoke is False
    assert runs[0].summary_url == "/evaluations/runtime-run/summary"


def test_list_evaluation_runs_labels_smoke_runtime_subset_artifacts(tmp_path):
    runtime_run = tmp_path / "smoke-rule-20261002T150000Z"
    runtime_run.mkdir()
    (runtime_run / "runtime_subset.json").write_text(
        json.dumps(
            {
                "run_name": "smoke-rule-20261002T150000Z",
                "created_at": "2026-10-02T15:00:00Z",
                "task_ids": ["0", "1", "2"],
                "max_steps": 6,
                "results": [],
            }
        )
    )

    runs = list_evaluation_runs(tmp_path)

    assert len(runs) == 1
    assert runs[0].run_name == "smoke-rule-20261002T150000Z"
    assert runs[0].run_type == "runtime_subset"
    assert runs[0].run_group == "smoke"
    assert runs[0].is_smoke is True


def test_list_evaluation_runs_labels_representative_regression_artifacts(tmp_path):
    run_dir = tmp_path / "regression-rule-demo"
    run_dir.mkdir()
    (run_dir / "runtime_subset.json").write_text(
        json.dumps({"run_name": "regression-rule-demo", "results": []})
    )

    run = list_evaluation_runs(tmp_path)[0]

    assert run.run_group == "regression"
    assert run.is_smoke is False


def test_list_evaluation_runs_returns_empty_for_missing_directory(tmp_path):
    runs = list_evaluation_runs(tmp_path / "missing")

    assert runs == []
