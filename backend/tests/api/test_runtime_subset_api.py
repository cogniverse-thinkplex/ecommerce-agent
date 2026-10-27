from fastapi.testclient import TestClient

from app.api.main import create_app
from app.agent.proposal_generator import ModelProviderError


def test_runtime_subset_api_runs_selected_retail_tasks():
    response = TestClient(create_app()).post(
        "/evaluations/runtime-subset",
        json={"task_ids": ["0"], "max_steps": 6, "planner_type": "rule"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["task_id"] == "0"
    assert body["results"][0]["planner_type"] == "rule"
    assert body["results"][0]["stopped_reason"] == "pending_confirmation"
    assert body["results"][0]["check"]["matched_prefix_count"] >= 4
    assert body["results"][0]["check"]["unexpected_actions"] == []
    assert body["results"][0]["diagnostic"]["message"] == "动作序列完全匹配。"
    assert body["results"][0]["trace_entries"]
    assert body["results"][0]["action_timeline"][0]["trace_sequence"] is not None


def test_runtime_subset_api_validates_empty_task_ids():
    response = TestClient(create_app()).post(
        "/evaluations/runtime-subset",
        json={"task_ids": [], "max_steps": 6},
    )

    assert response.status_code == 422


def test_runtime_subset_api_reports_llm_quota_exhaustion(monkeypatch):
    def exhausted_subset(*args, **kwargs):
        raise ModelProviderError(
            model="dashscope/qwen3.8-flash",
            reason="quota_exhausted",
        )

    monkeypatch.setattr(
        "app.api.main.run_retail_task_subset",
        exhausted_subset,
    )

    response = TestClient(create_app()).post(
        "/evaluations/runtime-subset",
        json={"task_ids": ["0"], "max_steps": 6, "planner_type": "llm"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "模型 dashscope/qwen3.8-flash 的可用额度已耗尽，"
        "请切换模型或调整百炼的免费额度限制。"
    )


def test_runtime_subset_api_can_confirm_and_verify_database_change():
    response = TestClient(create_app()).post(
        "/evaluations/runtime-subset",
        json={
            "task_ids": ["0"],
            "max_steps": 12,
            "planner_type": "rule",
            "verify_outcome_execution": True,
        },
    )

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["outcome_verification_mode"] == "confirmed_state"
    assert result["check"]["confirmed_outcome_success"] is True
    assert result["check"]["outcome"]["state_changed"] is True


def test_runtime_subset_api_can_save_and_read_artifact(tmp_path, monkeypatch):
    monkeypatch.setenv("ECOM_AGENT_SIMULATIONS_DIR", str(tmp_path))
    client = TestClient(create_app())

    response = client.post(
        "/evaluations/runtime-subset",
        json={
            "task_ids": ["0"],
            "max_steps": 6,
            "save_artifact": True,
            "run_name": "runtime-subset-demo",
            "planner_type": "rule",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["artifact"]["run_name"] == "runtime-subset-demo"
    assert body["artifact"]["planner_type"] == "rule"
    assert body["artifact_url"] == "/evaluations/runtime-subset/runtime-subset-demo"
    assert (tmp_path / "runtime-subset-demo" / "runtime_subset.json").exists()

    artifact_response = client.get("/evaluations/runtime-subset/runtime-subset-demo")

    assert artifact_response.status_code == 200
    artifact = artifact_response.json()
    assert artifact["task_ids"] == ["0"]
    assert artifact["planner_type"] == "rule"
    assert artifact["results"][0]["task_id"] == "0"
    assert artifact["results"][0]["trace_entries"]
    assert artifact["results"][0]["action_timeline"][0]["expected_action"] == (
        "find_user_id_by_name_zip"
    )
