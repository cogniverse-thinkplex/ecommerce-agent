import json

from fastapi.testclient import TestClient

from app.api.main import create_app


def test_smoke_compare_api_returns_task_diffs(tmp_path, monkeypatch):
    _write_runtime_subset(tmp_path / "smoke-rule-old" / "runtime_subset.json", True)
    _write_runtime_subset(tmp_path / "smoke-rule-new" / "runtime_subset.json", False)
    monkeypatch.setenv("ECOM_AGENT_SIMULATIONS_DIR", str(tmp_path))

    response = TestClient(create_app()).get(
        "/evaluations/smoke/compare",
        params={
            "baseline_run": "smoke-rule-old",
            "candidate_run": "smoke-rule-new",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["baseline_run"] == "smoke-rule-old"
    assert body["candidate_run"] == "smoke-rule-new"
    assert body["regression_count"] == 1
    assert body["task_diffs"][0]["status"] == "regression"


def _write_runtime_subset(path, exact_match):
    path.parent.mkdir()
    path.write_text(
        json.dumps(
            {
                "run_name": path.parent.name,
                "created_at": "2026-10-03T00:00:00Z",
                "task_ids": ["0"],
                "max_steps": 6,
                "results": [
                    {
                        "task_id": "0",
                        "conversation_id": "retail-task-0",
                        "stopped_reason": "pending_confirmation" if exact_match else "no_proposal",
                        "check": {
                            "task_id": "0",
                            "expected_actions": ["a"],
                            "actual_actions": ["a"] if exact_match else [],
                            "matched_prefix_count": 1 if exact_match else 0,
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
                            "category": "pending_confirmation" if exact_match else "action_deviation",
                            "recommended_action": "check",
                        },
                    }
                ],
            }
        )
    )
