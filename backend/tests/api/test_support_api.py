from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.agent.runtime import AgentAutoRunResult
from app.agent.state import ConversationMessage, CustomerAgentState
from app.auth.passwords import hash_password
from app.auth.service import AuthService
from app.persistence.sqlite import SqliteUnitOfWork
from app.persistence.models import UserRecord
from app.support.service import SupportService


class EchoAgent:
    def __init__(self) -> None:
        self.states = {}

    def start_session(self, conversation_id, *, authenticated_user_id=None):
        state = CustomerAgentState(
            conversation_id=conversation_id,
            messages=(
                [
                    ConversationMessage(
                        role="tool",
                        tool_name="find_user_id_by_email",
                        tool_call_id="platform-account-link",
                        content=authenticated_user_id,
                    )
                ]
                if authenticated_user_id
                else []
            ),
        )
        self.states[conversation_id] = state
        return state

    def get_session(self, conversation_id):
        return self.states[conversation_id]

    def auto_run(self, conversation_id, content, max_steps=6):
        state = self.states[conversation_id].model_copy(
            update={
                "messages": [
                    *self.states[conversation_id].messages,
                    ConversationMessage(role="user", content=content),
                    ConversationMessage(role="assistant", content=f"收到：{content}"),
                ]
            }
        )
        self.states[conversation_id] = state
        return AgentAutoRunResult(state=state, turns=[], stopped_reason="no_proposal")


def _client(tmp_path: Path) -> TestClient:
    unit = SqliteUnitOfWork(tmp_path / "support.db")
    unit.initialize()
    support = SupportService(EchoAgent(), unit)
    return TestClient(create_app(support_service=support))


def test_support_conversation_message_and_history_lifecycle(tmp_path: Path):
    client = _client(tmp_path)

    created = client.post("/api/v1/support/conversations")
    assert created.status_code == 201
    conversation_id = created.json()["conversation_id"]

    turn = client.post(
        f"/api/v1/support/conversations/{conversation_id}/messages",
        json={"content": "查询订单", "request_id": "request-1"},
    )
    history = client.get(
        f"/api/v1/support/conversations/{conversation_id}/messages"
    )
    index = client.get("/api/v1/support/conversations")

    assert turn.status_code == 200
    assert turn.json()["blocks"] == [
        {"type": "text", "title": None, "text": "收到：查询订单", "data": {}}
    ]
    assert [item["text"] for item in history.json()["messages"]] == [
        "您好，我是在线客服。请提供邮箱，或姓名和邮编以验证身份。",
        "查询订单",
        "收到：查询订单",
    ]
    assert index.json()["conversations"][0]["conversation_id"] == conversation_id
    assert index.json()["conversations"][0]["title"] == "查询订单"
    assert index.json()["conversations"][0]["message_count"] == 1
    assert index.json()["conversations"][0]["last_question_at"] is not None


def test_support_archive_hides_conversation(tmp_path: Path):
    client = _client(tmp_path)
    conversation_id = client.post("/api/v1/support/conversations").json()[
        "conversation_id"
    ]

    response = client.delete(f"/api/v1/support/conversations/{conversation_id}")

    assert response.status_code == 204
    assert client.get(f"/api/v1/support/conversations/{conversation_id}").status_code == 404


def test_linked_customer_login_creates_authenticated_conversation(tmp_path: Path):
    unit = SqliteUnitOfWork(tmp_path / "support-auth.db")
    unit.initialize()
    with unit.transaction():
        unit.users.create(
            UserRecord(
                user_id="demo-retail-ivan-santos",
                email="ivan.santos3158@example.com",
                display_name="Ivan Santos",
                password_hash=hash_password("DemoCustomer@123"),
                role="customer",
                retail_user_id="ivan_santos_6635",
            )
        )
    support = SupportService(EchoAgent(), unit)
    client = TestClient(
        create_app(
            support_service=support,
            auth_service=AuthService(unit),
            auth_required=True,
        )
    )

    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "ivan.santos3158@example.com",
            "password": "DemoCustomer@123",
        },
    )
    created = client.post("/api/v1/support/conversations")

    assert login.status_code == 200
    assert created.status_code == 201
    assert created.json()["authenticated"] is True
    conversation_id = created.json()["conversation_id"]
    assert support._agent.states[conversation_id].messages[0].content == "ivan_santos_6635"


def test_conversation_management_and_empty_cleanup(tmp_path: Path):
    client = _client(tmp_path)
    first = client.post("/api/v1/support/conversations").json()
    second = client.post("/api/v1/support/conversations").json()

    conversations = client.get(
        "/api/v1/support/conversations",
        params={"active_conversation_id": second["conversation_id"]},
    ).json()["conversations"]
    assert [item["conversation_id"] for item in conversations] == [second["conversation_id"]]

    group = client.post(
        "/api/v1/support/conversation-groups", json={"name": "售后订单"}
    )
    assert group.status_code == 201
    group_id = group.json()["group_id"]

    updated = client.patch(
        f"/api/v1/support/conversations/{second['conversation_id']}",
        json={"title": "办公椅退款", "is_pinned": True, "group_id": group_id},
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "办公椅退款"
    assert updated.json()["title_source"] == "custom"
    assert updated.json()["is_pinned"] is True
    assert updated.json()["group_id"] == group_id

    deleted_group = client.delete(f"/api/v1/support/conversation-groups/{group_id}")
    assert deleted_group.status_code == 204
    assert client.get(f"/api/v1/support/conversations/{second['conversation_id']}").json()["group_id"] is None

    assert client.delete(f"/api/v1/support/conversations/{second['conversation_id']}").status_code == 204
    assert client.get(f"/api/v1/support/conversations/{second['conversation_id']}").status_code == 404


def test_custom_title_named_new_conversation_is_not_overwritten(tmp_path: Path):
    client = _client(tmp_path)
    conversation_id = client.post("/api/v1/support/conversations").json()["conversation_id"]
    assert client.patch(
        f"/api/v1/support/conversations/{conversation_id}", json={"title": "新会话"}
    ).status_code == 200

    client.post(
        f"/api/v1/support/conversations/{conversation_id}/messages",
        json={"content": "查询全部订单", "request_id": "custom-title"},
    )

    conversation = client.get(f"/api/v1/support/conversations/{conversation_id}").json()
    assert conversation["title"] == "新会话"
    assert conversation["title_source"] == "custom"

