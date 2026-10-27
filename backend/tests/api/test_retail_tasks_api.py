from fastapi.testclient import TestClient

from app.api.main import create_app


def test_retail_tasks_api_returns_task_summaries():
    response = TestClient(create_app()).get("/retail/tasks?limit=1")

    assert response.status_code == 200
    body = response.json()
    assert len(body["tasks"]) == 1
    assert body["tasks"][0]["task_id"] == "0"
    assert "exchange the mechanical keyboard" in body["tasks"][0]["reason_for_call"]
    assert body["tasks"][0]["known_info"] == "You are Yusuf Rossi in zip code 19122."
    assert body["tasks"][0]["expected_actions"][0]["name"] == "find_user_id_by_name_zip"


def test_retail_tasks_api_validates_limit():
    response = TestClient(create_app()).get("/retail/tasks?limit=0")

    assert response.status_code == 422
