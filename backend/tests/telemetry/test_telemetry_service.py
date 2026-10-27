from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from app.persistence.sqlite import SqliteUnitOfWork
from app.persistence.models import ConversationRecord
from app.agent.state import CustomerAgentState
from app.agent.proposal_generator import RuleBasedProposalGenerator
from app.agent.session_service import AgentSessionService
from app.tools.guarded_executor import GuardedRetailToolExecutor
from app.tools.retail_port import ToolBackendInfo
from app.telemetry.models import FinishRunCommand, RecordStepCommand, StartRunCommand
from app.telemetry.service import RunTelemetryService


NOW = datetime(2026, 10, 22, 8, 0, tzinfo=timezone.utc)


def _service(tmp_path):
    unit = SqliteUnitOfWork(tmp_path / "telemetry.db")
    unit.initialize()
    return RunTelemetryService(unit), unit


def test_telemetry_records_success_and_preserves_unknown_cost(tmp_path):
    service, unit = _service(tmp_path)
    run = service.start_run(
        StartRunCommand(
            conversation_id=None,
            source="benchmark",
            planner_type="llm",
            model="dashscope/deepseek-v4-flash-0731",
            tool_backend="tau2-retail-mcp",
            started_at=NOW,
        )
    )
    service.record_step(
        run.run_id,
        RecordStepCommand(
            kind="tool",
            name="get_order_details",
            status="succeeded",
            summary={"arguments": {"order_id": "#W1"}, "tool": "get_order_details"},
            started_at=NOW,
            finished_at=NOW + timedelta(milliseconds=20),
        ),
    )
    finished = service.finish_run(
        run.run_id,
        FinishRunCommand(
            status="succeeded",
            stopped_reason="final_response",
            business_success=True,
            prompt_tokens=100,
            completion_tokens=20,
            total_tokens=120,
            estimated_cost_cny=None,
            finished_at=NOW + timedelta(seconds=1),
        ),
    )

    assert finished.duration_ms == 1000
    assert finished.step_count == 1
    assert finished.estimated_cost_cny is None
    step = unit.agent_run_steps.list_for_run(run.run_id)[0]
    assert step.summary["arguments"] == "[REDACTED]"


def test_recover_stale_running_rows_marks_them_failed(tmp_path):
    service, unit = _service(tmp_path)
    run = service.start_run(
        StartRunCommand(
            source="support",
            planner_type="rule",
            tool_backend="tau2-retail-mcp",
            started_at=NOW,
        )
    )

    recovered = service.recover_stale_runs(NOW + timedelta(minutes=5))

    assert recovered == 1
    stored = unit.agent_runs.get(run.run_id)
    assert stored is not None
    assert stored.status == "failed"
    assert stored.error_code == "stale_run_recovered"


def test_parallel_step_writes_keep_unique_sequence(tmp_path):
    service, unit = _service(tmp_path)
    run = service.start_run(
        StartRunCommand(
            source="sandbox",
            planner_type="rule",
            tool_backend="tau2-retail-mcp",
            started_at=NOW,
        )
    )

    def write(index):
        return service.record_step(
            run.run_id,
            RecordStepCommand(
                kind="planner",
                name=f"step-{index}",
                status="succeeded",
                started_at=NOW,
                finished_at=NOW,
            ),
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(write, range(8)))

    assert [item.sequence for item in unit.agent_run_steps.list_for_run(run.run_id)] == list(
        range(1, 9)
    )


def test_telemetry_failure_does_not_replace_agent_result(tmp_path, monkeypatch):
    service, _ = _service(tmp_path)
    monkeypatch.setattr(service, "start_run", lambda command: (_ for _ in ()).throw(RuntimeError("db down")))

    result = service.safe_capture(lambda: "agent-result", source="support")

    assert result == "agent-result"


def test_safe_capture_does_not_retry_failed_operation(tmp_path):
    service, _ = _service(tmp_path)
    calls = []

    def fail():
        calls.append("called")
        raise RuntimeError("telemetry offline")

    assert service.safe_capture(fail, source="support") is None
    assert calls == ["called"]


def test_session_auto_run_persists_waiting_confirmation_telemetry(tmp_path):
    service, unit = _service(tmp_path)
    with unit.transaction():
        unit.conversations.save(
            ConversationRecord(
                conversation_id="conv-telemetry",
                state=CustomerAgentState(conversation_id="conv-telemetry"),
            )
        )
    agent = AgentSessionService(
        GuardedRetailToolExecutor(_NoToolPort()),
        proposal_generator=RuleBasedProposalGenerator(),
        telemetry_service=service,
        telemetry_source="support",
    )
    agent.start_session("conv-telemetry")

    result = agent.auto_run("conv-telemetry", "hello", max_steps=1)

    assert result.stopped_reason == "no_proposal"
    runs = unit.agent_runs.list_all()
    assert len(runs) == 1
    assert runs[0].conversation_id == "conv-telemetry"
    assert runs[0].source == "support"
    assert runs[0].status == "succeeded"
    assert runs[0].planner_type == "rule"


class _NoToolPort:
    @property
    def backend(self):
        return ToolBackendInfo(kind="test", name="test-retail", managed_by_mcp=False)

    @property
    def policy(self):
        return ""

    def list_tools(self):
        return []

    def call_tool(self, name, arguments, call_id=None):
        raise AssertionError("No tools should be called")
