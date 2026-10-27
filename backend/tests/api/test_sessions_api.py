import json

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.agent.session_service import AgentSessionService
from app.tools.guarded_executor import GuardedRetailToolExecutor
from app.tools.retail_port import RetailToolDefinition
from tests.agent.test_session_service import RecordingPort


def test_root_redirects_to_customer_support_center():
    client = TestClient(create_app(), follow_redirects=False)

    response = client.get("/")

    assert response.status_code == 307
    assert response.headers["location"] == "/support/"


def test_health_reports_product_components_without_secrets():
    client = TestClient(create_app())

    body = client.get("/health").json()

    assert body["status"] == "ok"
    assert body["database"] in {"memory", "sqlite"}
    assert body["model"] in {"rule", "llm"}
    assert body["tool_backend"]
    assert "key" not in json.dumps(body).lower()


def test_sessions_api_creates_session_and_records_user_message():
    client = TestClient(create_app())

    created = client.post("/sessions", json={"conversation_id": "conv-1"})
    message = client.post(
        "/sessions/conv-1/messages",
        json={"content": "I need help with my order"},
    )

    assert created.status_code == 201
    assert created.json()["conversation_id"] == "conv-1"
    assert message.status_code == 200
    assert message.json()["messages"][-1]["role"] == "user"
    assert message.json()["messages"][-1]["content"] == "I need help with my order"


def test_sessions_api_executes_real_tau_retail_read_tool():
    client = TestClient(create_app())
    client.post("/sessions", json={"conversation_id": "conv-1"})

    response = client.post(
        "/sessions/conv-1/tool-calls",
        json={
            "name": "find_user_id_by_name_zip",
            "arguments": {
                "first_name": "Yusuf",
                "last_name": "Rossi",
                "zip": "19122",
            },
            "call_id": "call-1",
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["executed"] is True
    assert body["confirmation_required"] is False
    assert body["state"]["messages"][-2]["role"] == "tool"
    assert body["state"]["messages"][-2]["content"] == "yusuf_rossi_9620"
    assert body["state"]["messages"][-1]["role"] == "assistant"
    assert body["state"]["messages"][-1]["content"] == "身份信息已确认。您可以继续查询订单或办理售后。"


def test_sessions_api_applies_real_tau_retail_tool_proposal():
    client = TestClient(create_app())
    client.post("/sessions", json={"conversation_id": "conv-1"})

    response = client.post(
        "/sessions/conv-1/tool-proposals",
        json={
            "tool_name": "find_user_id_by_name_zip",
            "arguments": {
                "first_name": "Yusuf",
                "last_name": "Rossi",
                "zip": "19122",
            },
            "rationale": "Find the user before looking up their order.",
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["accepted"] is True
    assert body["tool_result"]["executed"] is True
    assert body["state"]["messages"][-1]["content"] == "yusuf_rossi_9620"


def test_sessions_api_runs_agent_turn_with_rule_based_proposal():
    client = TestClient(create_app())
    client.post("/sessions", json={"conversation_id": "conv-1"})

    response = client.post(
        "/sessions/conv-1/turns",
        json={"content": "Please find user Yusuf Rossi zip 19122"},
    )

    body = response.json()
    assert response.status_code == 200
    assert body["proposal"]["tool_name"] == "find_user_id_by_name_zip"
    assert body["proposal_result"]["accepted"] is True
    assert body["state"]["messages"][0]["role"] == "user"
    assert body["state"]["messages"][-2]["content"] == "yusuf_rossi_9620"
    assert body["state"]["messages"][-1]["role"] == "assistant"
    assert body["state"]["messages"][-1]["content"] == "身份信息已确认。您可以继续查询订单或办理售后。"


def test_sessions_api_runs_agent_turn_with_order_lookup_proposal():
    client = TestClient(create_app())
    client.post("/sessions", json={"conversation_id": "conv-1"})

    response = client.post(
        "/sessions/conv-1/turns",
        json={"content": "Please check order #W2378156"},
    )

    body = response.json()
    assert response.status_code == 200
    assert body["proposal"]["tool_name"] == "get_order_details"
    assert body["proposal"]["arguments"] == {"order_id": "#W2378156"}
    assert body["proposal_result"]["accepted"] is True
    assert body["proposal_result"]["tool_result"]["executed"] is True
    assert body["state"]["messages"][-2]["role"] == "tool"
    assert body["state"]["messages"][-1]["role"] == "assistant"
    assert "订单 #W2378156 当前为已送达" in body["state"]["messages"][-1]["content"]
    assert "订单金额 $1,819.92" in body["state"]["messages"][-1]["content"]


def test_sessions_api_continues_from_order_to_product_details():
    client = TestClient(create_app())
    client.post("/sessions", json={"conversation_id": "conv-1"})
    client.post(
        "/sessions/conv-1/turns",
        json={"content": "Please check order #W2378156"},
    )

    response = client.post(
        "/sessions/conv-1/turns",
        json={
            "content": (
                "Please exchange the mechanical keyboard and smart thermostat "
                "from order #W2378156."
            )
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["proposal"]["tool_name"] == "get_product_details"
    assert body["proposal"]["arguments"] == {"product_id": "1656367028"}
    assert body["proposal_result"]["accepted"] is True
    assert body["proposal_result"]["tool_result"]["executed"] is True
    assert body["state"]["messages"][-2]["tool_name"] == "get_product_details"
    assert body["state"]["messages"][-1]["role"] == "assistant"


def test_sessions_api_requires_confirmation_for_rule_based_exchange_proposal():
    client = TestClient(create_app())
    client.post("/sessions", json={"conversation_id": "conv-1"})
    exchange_request = (
        "Please exchange the mechanical keyboard and smart thermostat "
        "from order #W2378156."
    )
    client.post("/sessions/conv-1/turns", json={"content": "Please check order #W2378156"})
    client.post("/sessions/conv-1/turns", json={"content": exchange_request})
    client.post("/sessions/conv-1/turns", json={"content": exchange_request})

    response = client.post(
        "/sessions/conv-1/turns",
        json={"content": exchange_request},
    )

    body = response.json()
    assert response.status_code == 200
    assert body["proposal"]["tool_name"] == "exchange_delivered_order_items"
    assert body["proposal"]["arguments"] == {
        "order_id": "#W2378156",
        "item_ids": ["1151293680", "4983901480"],
        "new_item_ids": ["7706410293", "7747408585"],
        "payment_method_id": "credit_card_9513926",
    }
    assert body["proposal_result"]["accepted"] is True
    assert body["proposal_result"]["tool_result"]["executed"] is False
    assert body["proposal_result"]["tool_result"]["confirmation_required"] is True
    assert body["state"]["confirmation"]["pending"]["name"] == "exchange_delivered_order_items"


def test_sessions_api_auto_runs_until_write_confirmation_is_needed():
    client = TestClient(create_app())
    client.post("/sessions", json={"conversation_id": "conv-1"})

    response = client.post(
        "/sessions/conv-1/auto-run",
        json={
            "content": (
                "Please exchange the mechanical keyboard and smart thermostat "
                "from order #W2378156."
            ),
            "max_steps": 6,
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["stopped_reason"] == "pending_confirmation"
    assert [turn["proposal"]["tool_name"] for turn in body["turns"]] == [
        "get_order_details",
        "get_product_details",
        "get_product_details",
        "exchange_delivered_order_items",
    ]
    assert body["state"]["confirmation"]["pending"]["name"] == (
        "exchange_delivered_order_items"
    )
    assert [
        message["role"]
        for message in body["state"]["messages"]
        if message["role"] == "user"
    ] == ["user"]


def test_sessions_api_checks_session_against_retail_task_expected_actions():
    client = TestClient(create_app())
    client.post("/sessions", json={"conversation_id": "conv-1"})
    client.post(
        "/sessions/conv-1/turns",
        json={"content": "Please find user Yusuf Rossi zip 19122"},
    )
    client.post(
        "/sessions/conv-1/auto-run",
        json={
            "content": (
                "Please exchange the mechanical keyboard and smart thermostat "
                "from order #W2378156."
            ),
            "max_steps": 6,
        },
    )

    response = client.get("/sessions/conv-1/retail-task-check/0")

    body = response.json()
    assert response.status_code == 200
    assert body["exact_match"] is True
    assert body["matched_prefix_count"] == 5
    assert body["missing_actions"] == []
    assert body["unexpected_actions"] == []
    assert body["actual_actions"] == [
        "find_user_id_by_name_zip",
        "get_order_details",
        "get_product_details",
        "get_product_details",
        "exchange_delivered_order_items",
    ]


def test_sessions_api_blocks_write_until_confirmation_then_executes_it():
    client = TestClient(create_app())
    client.post("/sessions", json={"conversation_id": "conv-1"})
    request = {
        "name": "cancel_pending_order",
        "arguments": {"order_id": "#W0000000", "reason": "ordered by mistake"},
        "call_id": "call-2",
    }

    pending = client.post("/sessions/conv-1/tool-calls", json=request)
    confirmed = client.post(
        "/sessions/conv-1/confirmations",
        json={"confirmed": True, "user_text": "yes"},
    )
    executed = client.post("/sessions/conv-1/tool-calls", json=request)

    assert pending.status_code == 200
    assert pending.json()["executed"] is False
    assert pending.json()["confirmation_required"] is True
    assert confirmed.status_code == 200
    assert confirmed.json()["confirmed"] is True
    assert executed.status_code == 200
    assert executed.json()["executed"] is True
    assert executed.json()["state"]["messages"][-2]["role"] == "tool"
    assert executed.json()["state"]["messages"][-1]["role"] == "assistant"


def test_sessions_api_confirms_pending_write_and_continues_objective():
    service = AgentSessionService(
        GuardedRetailToolExecutor(
            RecordingPort(
                [
                    RetailToolDefinition(
                        name="cancel_pending_order",
                        tool_type="write",
                        description="",
                        parameters_schema={},
                    )
                ]
            )
        )
    )
    client = TestClient(create_app(service=service))
    client.post("/sessions", json={"conversation_id": "conv-1"})
    client.post(
        "/sessions/conv-1/tool-calls",
        json={
            "name": "cancel_pending_order",
            "arguments": {"order_id": "#W0000000", "reason": "mistake"},
        },
    )

    response = client.post(
        "/sessions/conv-1/confirm-and-continue",
        json={
            "confirmed": True,
            "user_text": "confirm",
            "objective": "cancel order #W0000000",
            "max_steps": 1,
        },
    )

    assert response.status_code == 200
    assert response.json()["executed"]["executed"] is True
    assert response.json()["auto_run"]["stopped_reason"] == "no_proposal"


def test_sessions_api_returns_404_for_missing_session():
    client = TestClient(create_app())

    response = client.post(
        "/sessions/missing/messages",
        json={"content": "hello"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown conversation_id: missing"


def test_admin_reset_clears_sessions_and_rebuilds_tool_backend():
    created_ports: list[RecordingPort] = []

    def executor_factory() -> GuardedRetailToolExecutor:
        port = RecordingPort(
            [
                RetailToolDefinition(
                    name=f"tool-{len(created_ports)}",
                    tool_type="read",
                    description="",
                    parameters_schema={},
                )
            ]
        )
        created_ports.append(port)
        return GuardedRetailToolExecutor(port)

    service = AgentSessionService(
        executor_factory(),
        executor_factory=executor_factory,
    )
    client = TestClient(create_app(service=service))
    client.post("/sessions", json={"conversation_id": "conv-1"})

    response = client.post("/admin/reset")

    assert response.status_code == 200
    assert response.json() == {
        "sessions_cleared": 1,
        "backend": {
            "kind": "recording",
            "name": "recording-retail",
            "managed_by_mcp": False,
        },
    }
    assert client.get("/sessions").json() == {"sessions": []}
    assert client.get("/tools").json()["tools"][0]["name"] == "tool-1"


def test_admin_reset_restores_real_tau_retail_order_state():
    client = TestClient(create_app())
    client.post("/sessions", json={"conversation_id": "conv-1"})

    initial_order = _call_tool(
        client,
        "conv-1",
        "get_order_details",
        {"order_id": "#W2378156"},
        call_id="initial-order",
    )
    assert initial_order["status"] == "delivered"

    return_request = {
        "name": "return_delivered_order_items",
        "arguments": {
            "order_id": "#W2378156",
            "item_ids": ["4602305039", "4202497723", "9408160950"],
            "payment_method_id": "credit_card_9513926",
        },
        "call_id": "return-demo",
    }
    pending = client.post("/sessions/conv-1/tool-calls", json=return_request)
    assert pending.status_code == 200
    assert pending.json()["confirmation_required"] is True
    confirmed = client.post(
        "/sessions/conv-1/confirmations",
        json={"confirmed": True, "user_text": "confirm"},
    )
    assert confirmed.status_code == 200
    executed = client.post("/sessions/conv-1/tool-calls", json=return_request)
    assert executed.status_code == 200
    assert executed.json()["executed"] is True
    assert executed.json()["state"]["messages"][-2]["role"] == "tool"
    assert executed.json()["state"]["messages"][-1]["role"] == "assistant"

    mutated_order = _call_tool(
        client,
        "conv-1",
        "get_order_details",
        {"order_id": "#W2378156"},
        call_id="mutated-order",
    )
    assert mutated_order["status"] == "return requested"

    reset = client.post("/admin/reset")
    assert reset.status_code == 200
    client.post("/sessions", json={"conversation_id": "conv-2"})
    restored_order = _call_tool(
        client,
        "conv-2",
        "get_order_details",
        {"order_id": "#W2378156"},
        call_id="restored-order",
    )

    assert reset.json()["sessions_cleared"] == 1
    assert restored_order["status"] == "delivered"


def _call_tool(
    client: TestClient,
    conversation_id: str,
    name: str,
    arguments: dict,
    call_id: str,
) -> dict:
    response = client.post(
        f"/sessions/{conversation_id}/tool-calls",
        json={"name": name, "arguments": arguments, "call_id": call_id},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["executed"] is True
    tool_messages = [
        message for message in body["state"]["messages"] if message["role"] == "tool"
    ]
    assert tool_messages
    return json.loads(tool_messages[-1]["content"])
