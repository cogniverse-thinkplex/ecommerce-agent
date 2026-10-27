import json

from fastapi.testclient import TestClient

from app.api.main import create_app


def test_evaluation_summary_api_reads_results_file(tmp_path, monkeypatch):
    run_dir = tmp_path / "demo-run"
    run_dir.mkdir()
    (run_dir / "results.json").write_text(
        json.dumps(
            {
                "simulations": [
                    {
                        "task_id": "0",
                        "agent_cost": 0.2,
                        "user_cost": 0.05,
                        "reward_info": {"reward": 1.0},
                    }
                ]
            }
        )
    )
    monkeypatch.setenv("ECOM_AGENT_SIMULATIONS_DIR", str(tmp_path))

    client = TestClient(create_app())
    response = client.get("/evaluations/demo-run/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["run_name"] == "demo-run"
    assert body["run_type"] == "tau2"
    assert body["simulations"] == 1
    assert body["average_reward"] == 1.0
    assert body["total_cost"] == 0.25


def test_evaluation_summary_api_reads_runtime_subset_artifact(tmp_path, monkeypatch):
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
    monkeypatch.setenv("ECOM_AGENT_SIMULATIONS_DIR", str(tmp_path))

    response = TestClient(create_app()).get("/evaluations/runtime-run/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["run_type"] == "runtime_subset"
    assert body["average_reward"] == 1.0
    assert body["exact_match_rate"] == 1.0
    assert body["business_success_rate"] == 1.0


def test_evaluation_summary_api_returns_404_for_missing_run(tmp_path, monkeypatch):
    monkeypatch.setenv("ECOM_AGENT_SIMULATIONS_DIR", str(tmp_path))

    client = TestClient(create_app())
    response = client.get("/evaluations/missing/summary")

    assert response.status_code == 404
    assert response.json()["detail"] == "Evaluation run not found: missing"
