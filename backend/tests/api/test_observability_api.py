from pathlib import Path
from fastapi.testclient import TestClient

import sqlite3

from app.api.main import _exception_source, create_app
from app.auth.service import AuthService
from app.observability.service import ObservabilityService
from app.persistence.sqlite import SqliteUnitOfWork
from app.tools.mcp_retail_adapter import McpTransportError


def test_exception_source_classifies_runtime_boundaries():
    class PlannerFailure(RuntimeError):
        __module__ = "app.agent.runtime"

    assert _exception_source(McpTransportError("offline")) == "mcp"
    assert _exception_source(sqlite3.OperationalError("locked")) == "database"
    assert _exception_source(PlannerFailure("invalid proposal")) == "planner"
    assert _exception_source(RuntimeError("unexpected")) == "api"


def test_developer_can_list_issues_and_customer_cannot(tmp_path: Path):
    unit = SqliteUnitOfWork(tmp_path / "app.db"); unit.initialize()
    observed = ObservabilityService(unit)
    observed.capture_issue(source="api", severity="error", error_code="BROKEN", context={"path": "/test"})
    app = create_app(auth_service=AuthService(unit), observability_service=observed, auth_required=True)
    customer = TestClient(app); developer = TestClient(app)
    customer.post("/api/v1/auth/register", json={"email":"user@example.com","display_name":"User","password":"CustomerPass@123"})
    developer.post("/api/v1/auth/login", json={"email":"admin@local.dev","password":"Admin@123456"})
    developer.post("/api/v1/auth/change-password", json={"current_password":"Admin@123456","new_password":"ChangedAdmin@123"})

    assert customer.get("/api/v1/observability/issues").status_code == 403
    response = developer.get("/api/v1/observability/issues")
    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_client_error_rejects_critical_severity(tmp_path: Path):
    unit = SqliteUnitOfWork(tmp_path / "app.db"); unit.initialize()
    app = create_app(auth_service=AuthService(unit), observability_service=ObservabilityService(unit), auth_required=True)
    client = TestClient(app)
    client.post("/api/v1/auth/register", json={"email":"user@example.com","display_name":"User","password":"CustomerPass@123"})
    response = client.post("/api/v1/observability/client-errors", json={"error_code":"FETCH_FAILED","summary":"failed","path":"/support/","severity":"critical"})
    assert response.status_code == 422


def test_customer_can_submit_required_issue_feedback_without_conversation(tmp_path: Path):
    unit = SqliteUnitOfWork(tmp_path / "app.db"); unit.initialize()
    app = create_app(auth_service=AuthService(unit), observability_service=ObservabilityService(unit), auth_required=True)
    client = TestClient(app)
    client.post("/api/v1/auth/register", json={"email":"user@example.com","display_name":"User","password":"CustomerPass@123"})

    response = client.post(
        "/api/v1/support/feedback",
        json={"category": "interface", "comment": "移动端按钮位置不便使用。"},
    )

    assert response.status_code == 201
    assert response.json()["conversation_id"] is None
    assert response.json()["rating"] == "not_helpful"
    assert response.json()["category"] == "interface"


def test_issue_feedback_requires_nonblank_bounded_description(tmp_path: Path):
    unit = SqliteUnitOfWork(tmp_path / "app.db"); unit.initialize()
    app = create_app(auth_service=AuthService(unit), observability_service=ObservabilityService(unit), auth_required=True)
    client = TestClient(app)
    client.post("/api/v1/auth/register", json={"email":"user@example.com","display_name":"User","password":"CustomerPass@123"})

    assert client.post("/api/v1/support/feedback", json={"category":"other", "comment":"   "}).status_code == 422
    assert client.post("/api/v1/support/feedback", json={"category":"other", "comment":"x" * 2001}).status_code == 422
