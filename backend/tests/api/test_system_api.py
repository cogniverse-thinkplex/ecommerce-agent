from fastapi.testclient import TestClient

from app.agent.proposal_generator import RuleBasedProposalGenerator
from app.agent.session_service import AgentSessionService
from app.api.main import create_app
from app.api.system import SystemStatusService
from app.auth.service import AuthService
from app.persistence.sqlite import SqliteUnitOfWork
from app.tools.guarded_executor import GuardedRetailToolExecutor
from app.tools.tau_retail_adapter import TauRetailAdapter


def test_system_status_is_developer_only_and_contains_no_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-should-never-appear")
    unit = SqliteUnitOfWork(tmp_path / "system.db")
    unit.initialize()
    agent = AgentSessionService(
        GuardedRetailToolExecutor(TauRetailAdapter.from_default_data()),
        proposal_generator=RuleBasedProposalGenerator(),
    )
    app = create_app(
        service=agent, auth_service=AuthService(unit),
        system_status_service=SystemStatusService(agent, unit), auth_required=True,
    )
    customer, developer = TestClient(app), TestClient(app)
    customer.post("/api/v1/auth/register", json={"email":"sys@example.com","display_name":"Sys","password":"CustomerPass@123"})
    developer.post("/api/v1/auth/login", json={"email":"admin@local.dev","password":"Admin@123456"})
    developer.post("/api/v1/auth/change-password", json={"current_password":"Admin@123456","new_password":"ChangedAdmin@123"})

    assert customer.get("/api/v1/system/status").status_code == 403
    response = developer.get("/api/v1/system/status")
    assert response.status_code == 200
    body = response.json()
    assert body["database"]["migration_version"] == 14
    assert body["agent"]["planner_type"] == "rule"
    assert body["tools"]["tool_count"] > 0
    assert "policy" not in body["agent"]
    assert "sk-should-never-appear" not in response.text


def test_system_status_degrades_when_tool_catalog_is_unavailable(tmp_path):
    unit = SqliteUnitOfWork(tmp_path / "degraded.db")
    unit.initialize()
    agent = AgentSessionService(
        GuardedRetailToolExecutor(TauRetailAdapter.from_default_data()),
        proposal_generator=RuleBasedProposalGenerator(),
    )
    agent.list_tools = lambda: (_ for _ in ()).throw(RuntimeError("secret transport detail"))

    payload = SystemStatusService(agent, unit).status()

    assert payload["status"] == "ok"
    assert payload["tools"]["status"] == "unavailable"
    assert payload["tools"]["tool_count"] == 0
    assert payload["tools"]["error_type"] == "RuntimeError"
    assert "secret transport detail" not in str(payload)
