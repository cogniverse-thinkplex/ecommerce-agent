from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.auth.service import AuthService
from app.persistence.models import AgentRunRecord
from app.persistence.sqlite import SqliteUnitOfWork
from app.telemetry.quality import QualityService


NOW = datetime(2026, 10, 22, tzinfo=timezone.utc)


def _clients(tmp_path):
    unit = SqliteUnitOfWork(tmp_path / "quality-api.db")
    unit.initialize()
    with unit.transaction():
        unit.agent_runs.create(
            AgentRunRecord(
                run_id="run-1",
                source="support",
                planner_type="rule",
                tool_backend="mcp",
                status="succeeded",
                started_at=NOW,
                finished_at=NOW + timedelta(seconds=1),
                duration_ms=1000,
            )
        )
    app = create_app(
        auth_service=AuthService(unit),
        quality_service=QualityService(unit),
        auth_required=True,
    )
    customer = TestClient(app)
    developer = TestClient(app)
    customer.post("/api/v1/auth/register", json={"email":"quality@example.com","display_name":"Quality User","password":"CustomerPass@123"})
    developer.post("/api/v1/auth/login", json={"email":"admin@local.dev","password":"Admin@123456"})
    developer.post("/api/v1/auth/change-password", json={"current_password":"Admin@123456","new_password":"ChangedAdmin@123"})
    return customer, developer


def test_quality_overview_is_developer_only_and_supports_empty_window(tmp_path):
    customer, developer = _clients(tmp_path)

    assert customer.get("/api/v1/quality/overview").status_code == 403
    response = developer.get("/api/v1/quality/overview?range=24h")

    assert response.status_code == 200
    body = response.json()
    assert body["total_runs"] in {0, 1}
    assert body["cost_available"] is False


def test_developer_can_list_and_open_runs(tmp_path):
    _, developer = _clients(tmp_path)

    listing = developer.get("/api/v1/runs?limit=10")
    detail = developer.get("/api/v1/runs/run-1")
    missing = developer.get("/api/v1/runs/missing")

    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert detail.status_code == 200
    assert detail.json()["run"]["run_id"] == "run-1"
    assert detail.json()["steps"] == []
    assert missing.status_code == 404


def test_developer_can_read_quality_trends(tmp_path):
    _, developer = _clients(tmp_path)

    response = developer.get("/api/v1/quality/trends?range=all")

    assert response.status_code == 200
    assert response.json()["items"][0]["date"] == "2026-10-22"


def test_developer_can_read_operational_observability(tmp_path):
    customer, developer = _clients(tmp_path)
    assert customer.get("/api/v1/quality/operations?range=all").status_code == 403
    response = developer.get("/api/v1/quality/operations?range=all")
    assert response.status_code == 200
    body = response.json()
    assert {"rag", "latency", "alerts", "versions"} <= body.keys()
