from fastapi.testclient import TestClient

from app.api.main import create_app


def test_session_audit_api_returns_confirmation_and_execution_evidence():
    client = TestClient(create_app())
    client.post("/sessions", json={"conversation_id": "audit-demo"})
    request = {
        "name": "cancel_pending_order",
        "arguments": {"order_id": "#W5918442", "reason": "ordered by mistake"},
    }
    client.post("/sessions/audit-demo/tool-calls", json=request)
    client.post(
        "/sessions/audit-demo/confirmations",
        json={"confirmed": True, "user_text": "yes"},
    )
    client.post("/sessions/audit-demo/tool-calls", json=request)

    response = client.get("/sessions/audit-demo/audit")

    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"] == "audit-demo"
    assert body["summary"]["total_objectives"] == 1
    assert body["objectives"][0]["tool_name"] == "cancel_pending_order"
    assert body["objectives"][0]["confirmation_status"] == "confirmed"
    assert body["objectives"][0]["execution_status"] == "succeeded"
    assert body["objectives"][0]["state_verification"] == "changed"
    assert [entry["kind"] for entry in body["timeline"]] == [
        "confirmation_requested",
        "confirmed",
        "executed",
    ]


def test_session_audit_api_returns_404_for_missing_session():
    client = TestClient(create_app())

    response = client.get("/sessions/missing/audit")

    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown conversation_id: missing"
