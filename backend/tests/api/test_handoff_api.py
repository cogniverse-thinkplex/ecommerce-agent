from pathlib import Path

from fastapi.testclient import TestClient

from app.agent.state import CustomerAgentState
from app.api.main import create_app
from app.auth.service import AuthService
from app.persistence.sqlite import SqliteUnitOfWork
from app.support.handoff import HumanHandoffService
from app.support.service import SupportService


class SessionOnlyAgent:
    def __init__(self):
        self.states = {}

    def start_session(self, conversation_id, *, authenticated_user_id=None):
        state = CustomerAgentState(conversation_id=conversation_id)
        self.states[conversation_id] = state
        return state


def test_customer_creates_handoff_and_developer_claims_and_resolves(tmp_path: Path):
    unit = SqliteUnitOfWork(tmp_path / "handoff-api.db")
    unit.initialize()
    handoffs = HumanHandoffService(unit)
    client = TestClient(
        create_app(
            support_service=SupportService(
                SessionOnlyAgent(), unit, handoff_service=handoffs
            ),
            auth_service=AuthService(unit),
            handoff_service=handoffs,
            auth_required=True,
        )
    )
    registered = client.post(
        "/api/v1/auth/register",
        json={
            "email": "customer@example.com",
            "display_name": "Customer",
            "password": "CustomerPass@123",
        },
    )
    assert registered.status_code == 201
    conversation_id = client.post("/api/v1/support/conversations").json()[
        "conversation_id"
    ]

    created = client.post(
        f"/api/v1/support/conversations/{conversation_id}/handoff",
        json={"reason": "customer_requested", "message": "请安排人工客服。"},
    )
    duplicate = client.post(
        f"/api/v1/support/conversations/{conversation_id}/handoff",
        json={"reason": "customer_requested", "message": "再次申请。"},
    )

    assert created.status_code == 201
    assert duplicate.json()["ticket_id"] == created.json()["ticket_id"]
    blocked_confirmation = client.post(
        f"/api/v1/support/conversations/{conversation_id}/actions/action-1/confirm",
        json={"request_id": "confirm-during-handoff"},
    )
    assert blocked_confirmation.status_code == 409
    assert blocked_confirmation.json()["detail"] == {
        "code": "human_handoff_active",
        "message": "人工服务处理中，暂时不能执行账户变更操作。",
        "recoverable": True,
    }
    client.post("/api/v1/auth/logout")
    client.post(
        "/api/v1/auth/login",
        json={"email": "admin@local.dev", "password": "Admin@123456"},
    )
    client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": "Admin@123456",
            "new_password": "ChangedAdmin@123",
        },
    )
    tickets = client.get("/api/v1/admin/handoffs")
    ticket_id = created.json()["ticket_id"]
    claimed = client.post(f"/api/v1/admin/handoffs/{ticket_id}/claim")
    resolved = client.post(f"/api/v1/admin/handoffs/{ticket_id}/resolve")

    assert tickets.status_code == 200
    assert tickets.json()["handoffs"][0]["ticket_id"] == ticket_id
    assert claimed.json()["status"] == "in_progress"
    assert resolved.json()["status"] == "resolved"
