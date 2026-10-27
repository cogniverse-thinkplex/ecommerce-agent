import json

from fastapi.testclient import TestClient

from app.api.main import create_app


def test_evaluations_api_lists_available_runs(tmp_path, monkeypatch):
    run_dir = tmp_path / "demo-run"
    run_dir.mkdir()
    (run_dir / "results.json").write_text(
        json.dumps({"simulations": [{"task_id": "0"}]})
    )
    monkeypatch.setenv("ECOM_AGENT_SIMULATIONS_DIR", str(tmp_path))

    client = TestClient(create_app())
    response = client.get("/evaluations")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "runs": [
            {
                "run_name": "demo-run",
                "has_results": True,
                "run_type": "tau2",
                "run_group": "adhoc",
                "is_smoke": False,
                "summary_url": "/evaluations/demo-run/summary",
                "updated_at": body["runs"][0]["updated_at"],
            }
        ]
    }
    assert body["runs"][0]["updated_at"] is not None


def test_evaluations_api_lists_runtime_subset_artifacts(tmp_path, monkeypatch):
    run_dir = tmp_path / "runtime-run"
    run_dir.mkdir()
    (run_dir / "runtime_subset.json").write_text(
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
    monkeypatch.setenv("ECOM_AGENT_SIMULATIONS_DIR", str(tmp_path))

    response = TestClient(create_app()).get("/evaluations")

    assert response.status_code == 200
    body = response.json()
    assert body["runs"][0]["run_name"] == "runtime-run"
    assert body["runs"][0]["run_type"] == "runtime_subset"
    assert body["runs"][0]["run_group"] == "adhoc"
    assert body["runs"][0]["is_smoke"] is False
    assert body["runs"][0]["summary_url"] == "/evaluations/runtime-run/summary"
