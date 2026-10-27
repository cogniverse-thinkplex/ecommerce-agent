from app.auth.models import AuthenticatedUser
from app.persistence.sqlite import SqliteUnitOfWork
from app.persistence.models import RuntimeIssueRecord, UserRecord
from app.regression.models import RegressionCaseCreate, RegressionCaseUpdate
from app.regression.service import RegressionCaseInvalid, RegressionService


ACTOR = AuthenticatedUser(user_id="developer-1", email="dev@example.com", display_name="Dev", role="developer", status="active", must_change_password=False)


def _service(tmp_path, executor=None):
    unit = SqliteUnitOfWork(tmp_path / "regression.db")
    unit.initialize()
    with unit.transaction():
        unit.users.create(UserRecord(user_id=ACTOR.user_id, email=ACTOR.email, display_name=ACTOR.display_name, password_hash="test", role="developer"))
    return RegressionService(unit, executor=executor), unit


def test_draft_can_be_incomplete_but_activation_requires_fixture_and_expectation(tmp_path):
    service, _ = _service(tmp_path)
    case = service.create_case(ACTOR, RegressionCaseCreate(name="Missing details"))

    assert case.status == "draft"
    try:
        service.update_case(case.case_id, RegressionCaseUpdate(status="active"))
    except RegressionCaseInvalid as exc:
        assert "预期" in str(exc)
    else:
        raise AssertionError("invalid case was activated")


def test_active_tau2_case_runs_and_persists_result(tmp_path):
    service, unit = _service(tmp_path, executor=lambda case, command: ("passed", None, None))
    case = service.create_case(
        ACTOR,
        RegressionCaseCreate(
            name="Tau2 task 0",
            origin_type="tau2",
            origin_id="0",
            fixture_type="tau2_task",
            fixture={"task_id": "0", "split": "base"},
            expected={"business_success": True},
            status="active",
        ),
    )

    batch = service.run_batch([case.case_id], planner_type="rule")

    assert batch.status == "passed"
    assert batch.results[0].status == "passed"
    assert unit.regression_case_runs.latest_for_case(case.case_id).status == "passed"
    run = unit.agent_runs.get(batch.results[0].agent_run_id)
    assert run.status == "succeeded"
    assert run.source == "regression"


def test_batch_marks_environment_failure_blocked_without_counting_it_failed(tmp_path):
    service, unit = _service(tmp_path, executor=lambda case, command: ("blocked", "MCP unavailable", None))
    case = service.create_case(
        ACTOR,
        RegressionCaseCreate(
            name="Replay",
            fixture_type="conversation_replay",
            fixture={"messages": [{"role": "user", "content": "hello"}]},
            expected={"response_required": True},
            status="active",
        ),
    )

    batch = service.run_batch([case.case_id], planner_type="rule")

    assert batch.status == "blocked"
    assert batch.failed_count == 0
    assert batch.blocked_count == 1
    assert unit.agent_runs.get(batch.results[0].agent_run_id).status == "cancelled"


def test_retired_case_cannot_run(tmp_path):
    service, _ = _service(tmp_path)
    case = service.create_case(
        ACTOR,
        RegressionCaseCreate(
            name="Retired",
            fixture={"task_id": "0"},
            expected={"business_success": True},
        ),
    )
    service.update_case(case.case_id, RegressionCaseUpdate(status="retired"))

    try:
        service.run_batch([case.case_id])
    except RegressionCaseInvalid as exc:
        assert "激活" in str(exc)
    else:
        raise AssertionError("retired case was run")


def test_issue_conversion_is_idempotent_and_redacts_fixture(tmp_path):
    service, unit = _service(tmp_path)
    with unit.transaction():
        unit.runtime_issues.upsert_occurrence(RuntimeIssueRecord(
            issue_id="issue-1", fingerprint="fingerprint", source="mcp",
            severity="error", error_code="TIMEOUT", summary="Tool timeout",
            context={"tool":"get_order_details", "api_key":"sk-secret"},
        ))

    first = service.create_from_issue(ACTOR, "issue-1")
    second = service.create_from_issue(ACTOR, "issue-1")

    assert first.case_id == second.case_id
    assert first.status == "draft"
    assert first.fixture["context"]["api_key"] == "[REDACTED]"


def test_verified_resolution_requires_latest_linked_case_to_pass(tmp_path):
    service, unit = _service(tmp_path, executor=lambda case, command: ("passed", None, None))
    with unit.transaction():
        unit.runtime_issues.upsert_occurrence(RuntimeIssueRecord(
            issue_id="issue-2", fingerprint="fingerprint-2", source="api",
            severity="error", error_code="BROKEN", summary="Broken",
        ))
    case = service.create_from_issue(ACTOR, "issue-2")

    assert service.issue_can_be_verified("issue-2") is False
    service.update_case(case.case_id, RegressionCaseUpdate(
        fixture={"task_id":"0"}, expected={"business_success":True}, status="active"
    ))
    service.run_batch([case.case_id])
    assert service.issue_can_be_verified("issue-2") is True
