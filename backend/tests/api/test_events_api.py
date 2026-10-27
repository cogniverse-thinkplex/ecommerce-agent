from fastapi.testclient import TestClient

from app.api.main import create_app


def test_events_api_returns_session_events_after_turn():
    client = TestClient(create_app())
    client.post("/sessions", json={"conversation_id": "conv-1"})
    client.post(
        "/sessions/conv-1/turns",
        json={"content": "Please find user Yusuf Rossi zip 19122"},
    )

    response = client.get("/sessions/conv-1/events")

    assert response.status_code == 200
    event_types = [event["event_type"] for event in response.json()["events"]]
    assert event_types == [
        "tool_proposal.accepted",
        "policy_guard.allowed",
        "tool_executor.executed",
        "response.quality_checked",
    ]


def test_events_api_filters_by_event_type_prefix():
    client = TestClient(create_app())
    client.post("/sessions", json={"conversation_id": "conv-1"})
    client.post(
        "/sessions/conv-1/turns",
        json={"content": "Please find user Yusuf Rossi zip 19122"},
    )

    response = client.get("/sessions/conv-1/events?event_type_prefix=policy_guard")

    assert response.status_code == 200
    events = response.json()["events"]
    assert len(events) == 1
    assert events[0]["event_type"] == "policy_guard.allowed"


def test_events_api_returns_404_for_missing_session():
    client = TestClient(create_app())

    response = client.get("/sessions/missing/events")

    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown conversation_id: missing"
