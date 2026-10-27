from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import create_app


def test_default_app_reloads_session_from_sqlite_after_restart(
    tmp_path: Path, monkeypatch
):
    database = tmp_path / "agent.db"
    monkeypatch.setenv("ECOM_AGENT_STORE", "sqlite")
    monkeypatch.setenv("ECOM_AGENT_SQLITE_PATH", str(database))
    monkeypatch.setenv("ECOM_AGENT_TOOL_BACKEND", "tau2_python")

    first = TestClient(create_app())
    assert first.post("/sessions", json={"conversation_id": "conv-1"}).status_code == 201
    assert first.post(
        "/sessions/conv-1/messages", json={"content": "persist me"}
    ).status_code == 200

    second = TestClient(create_app())
    response = second.get("/sessions/conv-1")

    assert response.status_code == 200
    assert response.json()["messages"][-1]["content"] == "persist me"

