from datetime import datetime, timedelta, timezone
import sqlite3

from app.persistence.models import (
    AgentRunRecord,
    AgentRunStepRecord,
    RegressionCaseRecord,
    RegressionCaseRunRecord,
)
from app.persistence.sqlite import SqliteUnitOfWork


NOW = datetime(2026, 10, 22, tzinfo=timezone.utc)


def _unit(tmp_path):
    unit = SqliteUnitOfWork(tmp_path / "quality.db")
    unit.initialize()
    return unit


def _run(run_id="run-1"):
    return AgentRunRecord(
        run_id=run_id,
        source="support",
        planner_type="llm",
        model="dashscope/deepseek-v4-flash-0731",
        tool_backend="tau2-retail-mcp",
        status="running",
        started_at=NOW,
    )


def test_migration_004_creates_quality_regression_schema(tmp_path):
    unit = _unit(tmp_path)

    assert unit.applied_migrations() == [1, 2, 3, 4, 5, 6, 7, 8, 12, 13, 14]
    tables = {
        row[0]
        for row in unit._connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert {
        "agent_runs",
        "agent_run_steps",
        "regression_cases",
        "regression_case_runs",
    } <= tables

    with unit.transaction():
        issue_columns = unit._connection.execute(
            "SELECT sql FROM sqlite_master WHERE name='runtime_issues'"
        ).fetchone()[0]
    assert "resolved_verified" in issue_columns


def test_agent_run_repository_completes_run_atomically(tmp_path):
    unit = _unit(tmp_path)
    with unit.transaction():
        unit.agent_runs.create(_run())
        completed = unit.agent_runs.finish(
            "run-1",
            status="succeeded",
            stopped_reason="final_response",
            business_success=True,
            step_count=2,
            prompt_tokens=120,
            completion_tokens=30,
            total_tokens=150,
            estimated_cost_cny=None,
            finished_at=NOW + timedelta(seconds=2),
            duration_ms=2000,
        )

    assert completed.status == "succeeded"
    assert completed.business_success is True
    assert completed.total_tokens == 150
    assert completed.estimated_cost_cny is None
    assert completed.duration_ms == 2000


def test_run_steps_allocate_monotonic_sequence(tmp_path):
    unit = _unit(tmp_path)
    with unit.transaction():
        unit.agent_runs.create(_run())
        first = unit.agent_run_steps.append(
            AgentRunStepRecord(
                step_id="step-1",
                run_id="run-1",
                sequence=0,
                kind="planner",
                name="decide",
                status="succeeded",
                started_at=NOW,
                finished_at=NOW,
                duration_ms=1,
            )
        )
        second = unit.agent_run_steps.append(
            AgentRunStepRecord(
                step_id="step-2",
                run_id="run-1",
                sequence=0,
                kind="tool",
                name="get_order_details",
                status="succeeded",
                summary={"tool": "get_order_details"},
                started_at=NOW,
                finished_at=NOW,
                duration_ms=3,
            )
        )

    assert (first.sequence, second.sequence) == (1, 2)
    assert [item.step_id for item in unit.agent_run_steps.list_for_run("run-1")] == [
        "step-1",
        "step-2",
    ]


def test_regression_case_origin_and_runs_round_trip(tmp_path):
    unit = _unit(tmp_path)
    case = RegressionCaseRecord(
        case_id="case-1",
        name="Exchange failure",
        description="Replays a failed exchange",
        origin_type="issue",
        origin_id="issue-1",
        fixture_type="tau2_task",
        fixture={"task_id": "0"},
        expected={"business_success": True},
        status="active",
        created_by_user_id=None,
        created_at=NOW,
        updated_at=NOW,
    )
    with unit.transaction():
        unit.regression_cases.create(case)
        unit.agent_runs.create(_run("run-case-1"))
        unit.regression_case_runs.create(
            RegressionCaseRunRecord(
                case_run_id="case-run-1",
                case_id="case-1",
                agent_run_id="run-case-1",
                batch_id="batch-1",
                status="passed",
                created_at=NOW,
                finished_at=NOW + timedelta(seconds=1),
            )
        )

    loaded = unit.regression_cases.get_by_origin("issue", "issue-1")
    latest = unit.regression_case_runs.latest_for_case("case-1")
    assert loaded == case
    assert latest is not None
    assert latest.status == "passed"

    with unit.transaction():
        unit.regression_cases.delete("case-1")
    assert unit.regression_case_runs.latest_for_case("case-1") is None


def test_regression_case_origin_is_unique(tmp_path):
    unit = _unit(tmp_path)
    case = RegressionCaseRecord(
        case_id="case-1",
        name="Issue replay",
        origin_type="issue",
        origin_id="issue-1",
        fixture_type="conversation_replay",
        fixture={},
        expected={},
        status="draft",
        created_at=NOW,
        updated_at=NOW,
    )
    with unit.transaction():
        unit.regression_cases.create(case)

    with sqlite3.connect(unit.path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            connection.execute(
                "INSERT INTO regression_cases "
                "(case_id,name,description,origin_type,origin_id,fixture_type,"
                "fixture_json,expected_json,status,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "case-2",
                    "Duplicate",
                    "",
                    "issue",
                    "issue-1",
                    "conversation_replay",
                    "{}",
                    "{}",
                    "draft",
                    NOW.isoformat(),
                    NOW.isoformat(),
                ),
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("Expected unique origin constraint")
