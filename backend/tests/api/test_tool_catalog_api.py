from fastapi.testclient import TestClient

from app.api.main import create_app


def test_tools_api_lists_real_tau_retail_tools():
    client = TestClient(create_app())

    response = client.get("/tools")

    assert response.status_code == 200
    body = response.json()
    assert body["backend"] == {
        "kind": "tau2_python",
        "name": "tau2-retail",
        "managed_by_mcp": False,
    }
    tools = {tool["name"]: tool for tool in body["tools"]}
    assert tools["find_user_id_by_name_zip"]["tool_type"] == "read"
    assert tools["cancel_pending_order"]["tool_type"] == "write"
    assert "parameters_schema" in tools["get_order_details"]


def test_policy_api_returns_real_tau_retail_policy():
    client = TestClient(create_app())

    response = client.get("/policy")

    assert response.status_code == 200
    assert "You can only help one user per conversation" in response.json()["policy"]
