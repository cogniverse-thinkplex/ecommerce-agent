from fastapi.testclient import TestClient

from app.api.main import create_app


def test_trace_api_returns_timeline_for_session_turn():
    client = TestClient(create_app())
    client.post("/sessions", json={"conversation_id": "conv-1"})
    client.post(
        "/sessions/conv-1/turns",
        json={"content": "Please find user Yusuf Rossi zip 19122"},
    )

    response = client.get("/sessions/conv-1/trace")

    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"] == "conv-1"
    assert body["pending_action"] is None
    assert body["confirmed_fingerprints"] == []
    assert [entry["sequence"] for entry in body["entries"]] == [1, 2, 3, 4, 5, 6, 7]
    assert [(entry["source"], entry["kind"]) for entry in body["entries"]] == [
        ("message", "user"),
        ("event", "tool_proposal.accepted"),
        ("event", "policy_guard.allowed"),
        ("event", "tool_executor.executed"),
        ("message", "tool"),
        ("message", "assistant"),
        ("event", "response.quality_checked"),
    ]
    assert body["entries"][-4]["payload"]["tool"] == "find_user_id_by_name_zip"
    assert body["entries"][-3]["tool_name"] == "find_user_id_by_name_zip"
    assert body["entries"][-3]["content"] == "yusuf_rossi_9620"
    assert body["entries"][-2]["content"] == "身份信息已确认。您可以继续查询订单或办理售后。"
    assert body["entries"][-1]["payload"]["passed"] is True


def test_trace_api_returns_404_for_missing_session():
    client = TestClient(create_app())

    response = client.get("/sessions/missing/trace")

    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown conversation_id: missing"
