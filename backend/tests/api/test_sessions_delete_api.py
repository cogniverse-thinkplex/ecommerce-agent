from fastapi.testclient import TestClient

from app.api.main import create_app


def test_delete_session_removes_active_session():
    client = TestClient(create_app())
    client.post("/sessions", json={"conversation_id": "conv-1"})

    deleted = client.delete("/sessions/conv-1")
    fetched = client.get("/sessions/conv-1")

    assert deleted.status_code == 204
    assert fetched.status_code == 404


def test_delete_session_returns_404_for_missing_session():
    client = TestClient(create_app())

    response = client.delete("/sessions/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown conversation_id: missing"
