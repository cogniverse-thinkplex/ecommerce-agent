from datetime import datetime, timedelta, timezone

from app.persistence.models import AgentRunRecord, AgentRunStepRecord
from app.persistence.sqlite import SqliteUnitOfWork
from app.telemetry.quality import QualityService, aggregate_operations, aggregate_quality, nearest_rank_percentile


NOW = datetime(2026, 10, 22, tzinfo=timezone.utc)


def _run(run_id, status, duration, **updates):
    started_at = updates.pop("started_at", NOW)
    finished_at = updates.pop(
        "finished_at",
        started_at + timedelta(milliseconds=duration) if duration is not None else None,
    )
    return AgentRunRecord(
        run_id=run_id,
        source="support",
        planner_type="llm",
        model="model-a",
        tool_backend="mcp",
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration,
        **updates,
    )


def test_nearest_rank_percentile_handles_empty_and_singleton_samples():
    assert nearest_rank_percentile([], 0.95) is None
    assert nearest_rank_percentile([42], 0.50) == 42
    assert nearest_rank_percentile([10, 20, 30, 40], 0.95) == 40


def test_quality_metrics_separate_waiting_confirmation_from_failures():
    runs = [
        _run("success", "succeeded", 100, business_success=True),
        _run("failure", "failed", 300, business_success=False),
        _run("waiting", "waiting_confirmation", 200),
        _run("active", "running", None),
    ]

    metrics = aggregate_quality(runs, [])

    assert metrics.total_runs == 4
    assert metrics.completed_runs == 2
    assert metrics.successful_runs == 1
    assert metrics.failed_runs == 1
    assert metrics.waiting_confirmation_runs == 1
    assert metrics.success_rate == 0.5
    assert metrics.error_rate == 0.5
    assert metrics.average_duration_ms == 200
    assert metrics.p50_duration_ms == 200
    assert metrics.p95_duration_ms == 300


def test_cancelled_environment_run_does_not_reduce_success_rate():
    metrics = aggregate_quality([
        _run("success", "succeeded", 100),
        _run("blocked", "cancelled", 50),
    ], [])

    assert metrics.completed_runs == 2
    assert metrics.success_rate == 1.0
    assert metrics.error_rate == 0.0


def test_quality_metrics_keep_token_totals_when_price_is_unknown():
    runs = [
        _run(
            "priced",
            "succeeded",
            100,
            prompt_tokens=100,
            completion_tokens=20,
            total_tokens=120,
            estimated_cost_cny=0.01,
        ),
        _run(
            "unknown-price",
            "succeeded",
            100,
            prompt_tokens=50,
            completion_tokens=10,
            total_tokens=60,
            estimated_cost_cny=None,
        ),
    ]

    metrics = aggregate_quality(runs, [])

    assert metrics.prompt_tokens == 150
    assert metrics.completion_tokens == 30
    assert metrics.total_tokens == 180
    assert metrics.token_usage_available is True
    assert metrics.cost_available is False
    assert metrics.total_estimated_cost_cny is None


def test_quality_metrics_rank_tool_calls_and_failures():
    runs = [_run("run-1", "succeeded", 100)]
    steps = [
        AgentRunStepRecord(step_id="1", run_id="run-1", sequence=1, kind="tool", name="get_order_details", status="succeeded"),
        AgentRunStepRecord(step_id="2", run_id="run-1", sequence=2, kind="tool", name="get_order_details", status="failed"),
        AgentRunStepRecord(step_id="3", run_id="run-1", sequence=3, kind="tool", name="find_user", status="succeeded"),
    ]

    metrics = aggregate_quality(runs, steps)

    assert metrics.tool_call_count == 3
    assert metrics.tool_failure_count == 1
    assert metrics.tool_failure_rate == 1 / 3
    assert metrics.tools[0].name == "get_order_details"
    assert metrics.tools[0].call_count == 2
    assert metrics.tools[0].failure_count == 1


def test_quality_trends_group_runs_by_utc_date(tmp_path):
    unit = SqliteUnitOfWork(tmp_path / "quality-trends.db")
    unit.initialize()
    with unit.transaction():
        unit.agent_runs.create(_run("run-1", "succeeded", 100))
        unit.agent_runs.create(
            _run(
                "run-2",
                "failed",
                300,
                started_at=NOW + timedelta(days=1),
                finished_at=NOW + timedelta(days=1, milliseconds=300),
            )
        )

    points = QualityService(unit).trends("all")

    assert [point.date for point in points] == ["2026-10-22", "2026-10-23"]
    assert points[0].successful_runs == 1
    assert points[1].failed_runs == 1


def test_operational_metrics_cover_rag_latency_alerts_and_versions():
    runs = [
        _run("run-1", "succeeded", 900, policy_version="policy-a", total_tokens=120, estimated_cost_cny=0.02),
        _run("run-2", "failed", 1500, policy_version="policy-b", error_code="ModelTimeout"),
    ]
    steps = [
        AgentRunStepRecord(step_id="1", run_id="run-1", sequence=1, kind="response", name="rag.completed", status="succeeded", duration_ms=80, summary={"hits":[{"policy_id":"returns","title":"退货规则","source_url":"https://example.com"}]}),
        AgentRunStepRecord(step_id="2", run_id="run-1", sequence=2, kind="response", name="response.quality_checked", status="succeeded", started_at=NOW + timedelta(milliseconds=300), summary={"policy_evidence_available":True}),
        AgentRunStepRecord(step_id="3", run_id="run-2", sequence=1, kind="response", name="rag.degraded", status="failed", duration_ms=120, summary={"reason":"EmbeddingUnavailable","hits":[]}),
        AgentRunStepRecord(step_id="4", run_id="run-2", sequence=2, kind="tool", name="get_order_details", status="failed", duration_ms=60),
    ]

    metrics = aggregate_operations(runs, steps, [])

    assert metrics.rag.request_count == 2
    assert metrics.rag.hit_rate == 0.5
    assert metrics.rag.degraded_count == 1
    assert metrics.rag.average_latency_ms == 100
    assert metrics.rag.policy_citation_rate == 1.0
    assert metrics.latency.average_first_response_ms == 300
    assert metrics.latency.average_complete_response_ms == 900
    assert metrics.latency.average_tool_ms == 60
    assert {alert.code for alert in metrics.alerts} == {"llm_timeout", "rag_degraded", "tool_failure"}
    assert {item.policy_version for item in metrics.versions} == {"policy-a", "policy-b"}


def test_operational_latency_uses_comparable_response_runs_and_ignores_zero_tool_timing():
    runs = [
        _run("answered", "succeeded", 1000),
        _run("no-response-step", "succeeded", 100),
    ]
    steps = [
        AgentRunStepRecord(step_id="response", run_id="answered", sequence=1, kind="response", name="response.quality_checked", status="succeeded", started_at=NOW + timedelta(milliseconds=250)),
        AgentRunStepRecord(step_id="zero-tool", run_id="answered", sequence=2, kind="tool", name="get_order_details", status="succeeded", duration_ms=0),
    ]
    metrics = aggregate_operations(runs, steps, [])
    assert metrics.latency.average_first_response_ms == 250
    assert metrics.latency.average_complete_response_ms == 1000
    assert metrics.latency.average_tool_ms is None


def test_run_detail_extracts_policy_and_business_evidence(tmp_path):
    unit = SqliteUnitOfWork(tmp_path / "quality-detail.db")
    unit.initialize()
    with unit.transaction():
        unit.agent_runs.create(_run("run-evidence", "succeeded", 100, business_success=True))
        unit.agent_run_steps.append(AgentRunStepRecord(step_id="rag", run_id="run-evidence", kind="response", name="rag.completed", status="succeeded", summary={"hits":[{"policy_id":"returns","title":"退货规则","source_url":"https://example.com"}]}))
    detail = QualityService(unit).get_run("run-evidence")
    assert detail.policy_evidence[0].policy_id == "returns"
    assert detail.business_outcome == "succeeded"
