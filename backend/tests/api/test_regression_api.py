from fastapi.testclient import TestClient

from app.api.main import create_app
from app.auth.service import AuthService
from app.persistence.sqlite import SqliteUnitOfWork
from app.persistence.models import RuntimeIssueRecord
from app.regression.service import RegressionService


def _clients(tmp_path):
    unit = SqliteUnitOfWork(tmp_path / "regression-api.db")
    unit.initialize()
    service = RegressionService(unit, executor=lambda case, command: ("passed", None, None))
    app = create_app(auth_service=AuthService(unit), regression_service=service, auth_required=True)
    customer = TestClient(app)
    developer = TestClient(app)
    customer.post("/api/v1/auth/register", json={"email":"reg@example.com","display_name":"Reg User","password":"CustomerPass@123"})
    developer.post("/api/v1/auth/login", json={"email":"admin@local.dev","password":"Admin@123456"})
    developer.post("/api/v1/auth/change-password", json={"current_password":"Admin@123456","new_password":"ChangedAdmin@123"})
    return customer, developer


def test_regression_case_crud_and_batch_are_developer_only(tmp_path):
    customer, developer = _clients(tmp_path)
    payload = {"name":"Task 0", "origin_type":"tau2", "origin_id":"0", "fixture_type":"tau2_task", "fixture":{"task_id":"0"}, "expected":{"business_success":True}, "status":"active"}

    assert customer.post("/api/v1/regression/cases", json=payload).status_code == 403
    created = developer.post("/api/v1/regression/cases", json=payload)
    assert created.status_code == 201
    case_id = created.json()["case_id"]
    assert developer.get("/api/v1/regression/cases").json()["total"] == 1

    batch = developer.post("/api/v1/regression/batches", json={"case_ids":[case_id], "planner_type":"rule"})
    assert batch.status_code == 201
    batch_id = batch.json()["batch_id"]
    assert developer.get(f"/api/v1/regression/batches/{batch_id}").json()["status"] == "passed"


def test_regression_api_returns_stable_errors(tmp_path):
    _, developer = _clients(tmp_path)

    assert developer.patch("/api/v1/regression/cases/missing", json={"status":"active"}).status_code == 404
    response = developer.post("/api/v1/regression/batches", json={"case_ids":["missing"]})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_regression_case"


def test_developer_can_convert_issue_to_draft(tmp_path):
    _, developer = _clients(tmp_path)
    app = developer.app
    unit = app.state.regression_service._unit
    with unit.transaction():
        unit.runtime_issues.upsert_occurrence(RuntimeIssueRecord(
            issue_id="issue-api", fingerprint="issue-api-fp", source="mcp",
            severity="error", error_code="MCP_DOWN", summary="MCP unavailable",
        ))

    response = developer.post("/api/v1/regression/cases/from-issue/issue-api")

    assert response.status_code == 201
    assert response.json()["origin_id"] == "issue-api"
