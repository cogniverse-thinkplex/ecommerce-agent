from fastapi.testclient import TestClient

from app.api.main import create_app


def test_sessions_index_api_lists_active_sessions():
    client = TestClient(create_app())
    client.post("/sessions", json={"conversation_id": "conv-a"})
    client.post("/sessions", json={"conversation_id": "conv-b"})
    client.post(
        "/sessions/conv-a/turns",
        json={"content": "Please find user Yusuf Rossi zip 19122"},
    )

    response = client.get("/sessions")

    assert response.status_code == 200
    assert response.json() == {
        "sessions": [
            {
                "conversation_id": "conv-a",
                "message_count": 3,
                "event_count": 4,
                "has_pending_action": False,
            },
            {
                "conversation_id": "conv-b",
                "message_count": 0,
                "event_count": 0,
                "has_pending_action": False,
            },
        ]
    }
