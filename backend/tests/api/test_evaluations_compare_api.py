import json

from fastapi.testclient import TestClient

from app.api.main import create_app


def test_evaluations_compare_api_returns_run_summaries(tmp_path, monkeypatch):
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

    response = TestClient(create_app()).get("/evaluations/compare")

    assert response.status_code == 200
    assert response.json() == {
        "runs": [
            {
                "run_name": "demo-run",
                "run_type": "tau2",
                "run_group": "adhoc",
                "is_smoke": False,
                "simulations": 1,
                "average_reward": 1.0,
                "cost_available": True,
                "total_cost": 0.25,
                "average_cost": 0.25,
                "exact_match_rate": None,
                "business_success_rate": None,
                "confirmation_gate_success_rate": None,
                "confirmed_outcome_success_rate": None,
                "average_matched_prefix_count": None,
                "average_step_count": None,
                "failure_categories": {},
            }
        ]
    }
