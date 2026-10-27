from app.auth.models import AuthenticatedUser
from app.observability.service import ObservabilityService
from app.persistence.models import UserRecord
from app.persistence.sqlite import SqliteUnitOfWork
from app.regression.models import RegressionCaseUpdate
from app.regression.service import RegressionService
from app.telemetry.quality import QualityService


def test_issue_to_passing_regression_to_verified_resolution(tmp_path):
    unit = SqliteUnitOfWork(tmp_path / "quality-flow.db")
    unit.initialize()
    actor = AuthenticatedUser(
        user_id="developer-flow", email="flow@example.com", display_name="Flow Dev",
        role="developer", status="active", must_change_password=False,
    )
    with unit.transaction():
        unit.users.create(UserRecord(
            user_id=actor.user_id, email=actor.email, display_name=actor.display_name,
            password_hash="test", role="developer",
        ))
    observed = ObservabilityService(unit)
    regression = RegressionService(unit, executor=lambda case, command: ("passed", None, None))

    observed.capture_issue(
        source="mcp", severity="error", error_code="CONTROLLED_FAILURE",
        context={"tool":"get_order_details", "api_key":"sk-never-store"},
    )
    issue = unit.runtime_issues.list_filtered()[0][0]
    case = regression.create_from_issue(actor, issue.issue_id)
    regression.update_case(case.case_id, RegressionCaseUpdate(
        fixture={"task_id":"0", "split":"base"},
        expected={"business_success":True}, status="active",
    ))
    batch = regression.run_batch([case.case_id])
    resolved = observed.review_issue(
        actor, issue.issue_id, status="resolved_verified",
        developer_note="Regression passed.",
    )

    assert batch.status == "passed"
    assert resolved["status"] == "resolved_verified"
    assert unit.regression_cases.get_by_origin("issue", issue.issue_id).case_id == case.case_id
    assert unit.agent_runs.get(batch.results[0].agent_run_id).source == "regression"
    assert QualityService(unit).overview("all").successful_runs == 1
    assert "sk-never-store" not in str(case.fixture)
