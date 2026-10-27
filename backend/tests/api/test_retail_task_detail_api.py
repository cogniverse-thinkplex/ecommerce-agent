from fastapi.testclient import TestClient

from app.api.main import create_app


def test_retail_task_detail_api_returns_expected_actions():
    response = TestClient(create_app()).get("/retail/tasks/0")

    assert response.status_code == 200
    body = response.json()
    assert body["task_id"] == "0"
    assert body["expected_actions"][0] == {
        "action_id": "0_0",
        "name": "find_user_id_by_name_zip",
        "arguments": {
            "first_name": "Yusuf",
            "last_name": "Rossi",
            "zip": "19122",
        },
    }


def test_retail_task_detail_api_returns_404_for_missing_task():
    response = TestClient(create_app()).get("/retail/tasks/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown retail task_id: missing"
