from pathlib import Path

from fastapi.testclient import TestClient

from app.agent.session_service import AgentSessionService
from app.agent.proposal_generator import RuleBasedProposalGenerator
from app.api.main import create_app
from app.auth.service import AuthService
from app.persistence.sqlite import SqliteUnitOfWork
from app.support.service import SupportService
from app.tools.guarded_executor import GuardedRetailToolExecutor
from app.tools.tau_retail_adapter import TauRetailAdapter


def test_customer_support_conversations_are_owner_scoped(tmp_path: Path):
    unit = SqliteUnitOfWork(tmp_path / "owned.db")
    unit.initialize()
    agent = AgentSessionService(
        GuardedRetailToolExecutor(TauRetailAdapter.from_default_data()),
        proposal_generator=RuleBasedProposalGenerator(),
    )
    app = create_app(
        service=agent,
        support_service=SupportService(agent, unit),
        auth_service=AuthService(unit),
        auth_required=True,
    )
    first = TestClient(app)
    second = TestClient(app)
    first.post(
        "/api/v1/auth/register",
        json={"email": "one@example.com", "display_name": "One", "password": "CustomerPass@123"},
    )
    second.post(
        "/api/v1/auth/register",
        json={"email": "two@example.com", "display_name": "Two", "password": "CustomerPass@123"},
    )

    conversation_id = first.post("/api/v1/support/conversations").json()["conversation_id"]

    assert len(first.get(
        "/api/v1/support/conversations",
        params={"active_conversation_id": conversation_id},
    ).json()["conversations"]) == 1
    assert second.get(f"/api/v1/support/conversations/{conversation_id}").status_code == 404
    assert second.get("/api/v1/support/conversations").json()["conversations"] == []

    group_id = first.post(
        "/api/v1/support/conversation-groups", json={"name": "我的订单"}
    ).json()["group_id"]
    assert second.patch(
        f"/api/v1/support/conversation-groups/{group_id}", json={"name": "越权"}
    ).status_code == 404
    assert second.delete(f"/api/v1/support/conversation-groups/{group_id}").status_code == 404
    assert second.patch(
        f"/api/v1/support/conversations/{conversation_id}", json={"group_id": group_id}
    ).status_code == 404

    deleted = first.delete(f"/api/v1/support/conversations/{conversation_id}")
    assert deleted.status_code == 204
    assert first.get(f"/api/v1/support/conversations/{conversation_id}").status_code == 404
    assert first.get("/api/v1/support/conversations").json()["conversations"] == []
