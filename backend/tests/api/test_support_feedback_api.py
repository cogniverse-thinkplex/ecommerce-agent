from pathlib import Path
from fastapi.testclient import TestClient
from app.agent.proposal_generator import RuleBasedProposalGenerator
from app.agent.session_service import AgentSessionService
from app.api.main import create_app
from app.auth.service import AuthService
from app.observability.service import ObservabilityService
from app.persistence.sqlite import SqliteUnitOfWork
from app.support.service import SupportService
from app.tools.guarded_executor import GuardedRetailToolExecutor
from app.tools.tau_retail_adapter import TauRetailAdapter


def test_customer_submits_feedback_for_owned_conversation(tmp_path: Path):
    unit = SqliteUnitOfWork(tmp_path / "app.db"); unit.initialize()
    agent = AgentSessionService(GuardedRetailToolExecutor(TauRetailAdapter.from_default_data()), proposal_generator=RuleBasedProposalGenerator())
    app = create_app(service=agent, support_service=SupportService(agent, unit), auth_service=AuthService(unit), observability_service=ObservabilityService(unit), auth_required=True)
    first, second = TestClient(app), TestClient(app)
    first.post("/api/v1/auth/register", json={"email":"one@example.com","display_name":"One","password":"CustomerPass@123"})
    second.post("/api/v1/auth/register", json={"email":"two@example.com","display_name":"Two","password":"CustomerPass@123"})
    cid = first.post("/api/v1/support/conversations").json()["conversation_id"]

    assert first.post(f"/api/v1/support/conversations/{cid}/feedback", json={"rating":"helpful","category":"resolved"}).status_code == 201
    assert second.post(f"/api/v1/support/conversations/{cid}/feedback", json={"rating":"helpful"}).status_code == 404
    payload = first.get(f"/api/v1/support/conversations/{cid}/feedback").json()
    assert len(payload["feedback"]) == 1
    assert "developer_note" not in payload["feedback"][0]
