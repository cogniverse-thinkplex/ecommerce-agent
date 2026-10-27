from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from math import ceil
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.persistence.models import AgentRunRecord, AgentRunStepRecord
from app.persistence.sqlite import SqliteUnitOfWork


class ToolQualityMetric(BaseModel):
    name: str
    call_count: int = 0
    failure_count: int = 0
    failure_rate: float = 0.0


class QualityOverview(BaseModel):
    total_runs: int = 0
    active_runs: int = 0
    completed_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    waiting_confirmation_runs: int = 0
    success_rate: float = 0.0
    error_rate: float = 0.0
    business_success_rate: float | None = None
    average_duration_ms: float | None = None
    p50_duration_ms: int | None = None
    p95_duration_ms: int | None = None
    average_step_count: float | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    token_usage_available: bool = False
    cost_available: bool = False
    total_estimated_cost_cny: float | None = None
    average_estimated_cost_cny: float | None = None
    tool_call_count: int = 0
    tool_failure_count: int = 0
    tool_failure_rate: float = 0.0
    tools: list[ToolQualityMetric] = Field(default_factory=list)


class QualityTrendPoint(BaseModel):
    date: str
    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    waiting_confirmation_runs: int = 0
    success_rate: float = 0.0
    average_duration_ms: float | None = None
    total_tokens: int = 0
    token_usage_available: bool = False
    total_estimated_cost_cny: float | None = None
    cost_available: bool = False


class RunPage(BaseModel):
    items: list[AgentRunRecord]
    total: int


class RunDetail(BaseModel):
    run: AgentRunRecord
    steps: list[AgentRunStepRecord]
    policy_evidence: list["PolicyEvidence"] = Field(default_factory=list)
    business_outcome: str


class PolicyEvidence(BaseModel):
    policy_id: str
    title: str = ""
    source_url: str = ""


class RagOperations(BaseModel):
    request_count: int = 0
    hit_count: int = 0
    hit_rate: float = 0.0
    degraded_count: int = 0
    degraded_rate: float = 0.0
    average_latency_ms: float | None = None
    policy_citation_count: int = 0
    policy_citation_rate: float | None = None


class LatencyOperations(BaseModel):
    average_first_response_ms: float | None = None
    average_complete_response_ms: float | None = None
    average_tool_ms: float | None = None
    average_handoff_resolution_ms: float | None = None


class OperationalAlert(BaseModel):
    code: str
    level: Literal["warning", "critical"]
    count: int
    message: str


class VersionMetric(BaseModel):
    model: str
    policy_version: str
    data_version: str
    run_count: int
    success_rate: float
    average_duration_ms: float | None = None
    average_tokens: float | None = None
    average_cost_cny: float | None = None


class OperationsOverview(BaseModel):
    rag: RagOperations
    latency: LatencyOperations
    alerts: list[OperationalAlert] = Field(default_factory=list)
    versions: list[VersionMetric] = Field(default_factory=list)


def nearest_rank_percentile(values: list[int], percentile: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def aggregate_quality(
    runs: list[AgentRunRecord],
    steps: list[AgentRunStepRecord],
) -> QualityOverview:
    finished = [run for run in runs if run.status in {"succeeded", "failed", "cancelled"}]
    assessed_runs = [run for run in finished if run.status in {"succeeded", "failed"}]
    successful = [run for run in assessed_runs if run.status == "succeeded"]
    failed = [run for run in assessed_runs if run.status == "failed"]
    waiting = [run for run in runs if run.status == "waiting_confirmation"]
    durations = [run.duration_ms for run in runs if run.duration_ms is not None]
    assessed = [run for run in runs if run.business_success is not None]
    token_runs = [run for run in runs if run.total_tokens is not None]
    costs = [run.estimated_cost_cny for run in runs if run.estimated_cost_cny is not None]
    all_costs_known = bool(costs) and all(
        run.planner_type == "rule" or run.estimated_cost_cny is not None
        for run in runs
    )
    tool_steps = [step for step in steps if step.kind == "tool"]
    tool_counts = Counter(step.name for step in tool_steps)
    tool_failures = Counter(step.name for step in tool_steps if step.status == "failed")
    tool_metrics = [
        ToolQualityMetric(
            name=name,
            call_count=count,
            failure_count=tool_failures[name],
            failure_rate=tool_failures[name] / count,
        )
        for name, count in sorted(tool_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    return QualityOverview(
        total_runs=len(runs), active_runs=sum(run.status == "running" for run in runs),
        completed_runs=len(finished), successful_runs=len(successful), failed_runs=len(failed),
        waiting_confirmation_runs=len(waiting),
        success_rate=len(successful) / len(assessed_runs) if assessed_runs else 0.0,
        error_rate=len(failed) / len(assessed_runs) if assessed_runs else 0.0,
        business_success_rate=(sum(bool(run.business_success) for run in assessed) / len(assessed) if assessed else None),
        average_duration_ms=sum(durations) / len(durations) if durations else None,
        p50_duration_ms=nearest_rank_percentile(durations, 0.50),
        p95_duration_ms=nearest_rank_percentile(durations, 0.95),
        average_step_count=sum(run.step_count for run in runs) / len(runs) if runs else None,
        prompt_tokens=sum(run.prompt_tokens or 0 for run in token_runs),
        completion_tokens=sum(run.completion_tokens or 0 for run in token_runs),
        total_tokens=sum(run.total_tokens or 0 for run in token_runs),
        token_usage_available=bool(token_runs), cost_available=all_costs_known,
        total_estimated_cost_cny=sum(costs) if all_costs_known else None,
        average_estimated_cost_cny=sum(costs) / len(costs) if all_costs_known and costs else None,
        tool_call_count=len(tool_steps),
        tool_failure_count=sum(step.status == "failed" for step in tool_steps),
        tool_failure_rate=(sum(step.status == "failed" for step in tool_steps) / len(tool_steps) if tool_steps else 0.0),
        tools=tool_metrics,
    )


def aggregate_operations(
    runs: list[AgentRunRecord],
    steps: list[AgentRunStepRecord],
    handoffs: list[Any],
) -> OperationsOverview:
    rag_steps = [step for step in steps if step.name in {"rag.completed", "rag.degraded"}]
    hit_steps = [step for step in rag_steps if bool(step.summary.get("hits"))]
    degraded_steps = [step for step in rag_steps if step.name == "rag.degraded"]
    rag_durations = [step.duration_ms for step in rag_steps if step.duration_ms is not None]
    quality_steps = [step for step in steps if step.name == "response.quality_checked"]
    hit_run_ids = {step.run_id for step in hit_steps}
    cited_run_ids = {
        step.run_id for step in quality_steps
        if step.summary.get("policy_evidence_available") and step.run_id in hit_run_ids
    }

    first_response_durations: list[int] = []
    response_run_ids: set[str] = set()
    for run in runs:
        response_steps = [
            step for step in quality_steps
            if step.run_id == run.run_id and step.started_at >= run.started_at
        ]
        if response_steps:
            first = min(step.started_at for step in response_steps)
            elapsed = max(0, int((first - run.started_at).total_seconds() * 1000))
            if run.duration_ms is None or elapsed <= run.duration_ms:
                first_response_durations.append(elapsed)
                response_run_ids.add(run.run_id)
    complete_durations = [
        run.duration_ms for run in runs
        if run.run_id in response_run_ids and run.duration_ms is not None
    ]
    tool_durations = [
        step.duration_ms for step in steps
        if step.kind == "tool" and step.duration_ms is not None and step.duration_ms > 0
    ]
    handoff_durations = [
        max(0, int((item.resolved_at - item.created_at).total_seconds() * 1000))
        for item in handoffs
        if item.resolved_at is not None
    ]

    alert_counts: Counter[str] = Counter()
    for run in runs:
        code = (run.error_code or "").lower()
        if "timeout" in code:
            alert_counts["llm_timeout"] += 1
        if any(word in code for word in ("quota", "credit", "balance", "rate_limit")):
            alert_counts["llm_quota"] += 1
        if "mcp" in code:
            alert_counts["mcp_failure"] += 1
    alert_counts["rag_degraded"] += len(degraded_steps)
    alert_counts["tool_failure"] += sum(
        step.kind == "tool" and step.status == "failed" for step in steps
    )
    alert_messages = {
        "llm_timeout": "LLM 请求发生超时",
        "llm_quota": "模型额度或限流异常",
        "mcp_failure": "MCP 工具后端异常",
        "rag_degraded": "政策检索已降级",
        "tool_failure": "工具调用失败",
    }
    alerts = [
        OperationalAlert(
            code=code,
            level="critical" if code in {"llm_quota", "mcp_failure"} else "warning",
            count=count,
            message=alert_messages[code],
        )
        for code, count in alert_counts.items() if count
    ]

    version_groups: dict[tuple[str, str, str], list[AgentRunRecord]] = {}
    for run in runs:
        key = (run.model or run.planner_type, run.policy_version or "未记录", run.data_version or "未记录")
        version_groups.setdefault(key, []).append(run)
    versions: list[VersionMetric] = []
    for (model, policy_version, data_version), group in version_groups.items():
        assessed = [item for item in group if item.status in {"succeeded", "failed"}]
        durations = [item.duration_ms for item in group if item.duration_ms is not None]
        tokens = [item.total_tokens for item in group if item.total_tokens is not None]
        costs = [item.estimated_cost_cny for item in group if item.estimated_cost_cny is not None]
        versions.append(VersionMetric(
            model=model,
            policy_version=policy_version,
            data_version=data_version,
            run_count=len(group),
            success_rate=(sum(item.status == "succeeded" for item in assessed) / len(assessed) if assessed else 0.0),
            average_duration_ms=(sum(durations) / len(durations) if durations else None),
            average_tokens=(sum(tokens) / len(tokens) if tokens else None),
            average_cost_cny=(sum(costs) / len(costs) if costs else None),
        ))
    versions.sort(key=lambda item: (-item.run_count, item.model, item.policy_version))
    return OperationsOverview(
        rag=RagOperations(
            request_count=len(rag_steps),
            hit_count=len(hit_steps),
            hit_rate=len(hit_steps) / len(rag_steps) if rag_steps else 0.0,
            degraded_count=len(degraded_steps),
            degraded_rate=len(degraded_steps) / len(rag_steps) if rag_steps else 0.0,
            average_latency_ms=sum(rag_durations) / len(rag_durations) if rag_durations else None,
            policy_citation_count=len(cited_run_ids),
            policy_citation_rate=(len(cited_run_ids) / len(hit_run_ids) if hit_run_ids else None),
        ),
        latency=LatencyOperations(
            average_first_response_ms=sum(first_response_durations) / len(first_response_durations) if first_response_durations else None,
            average_complete_response_ms=sum(complete_durations) / len(complete_durations) if complete_durations else None,
            average_tool_ms=sum(tool_durations) / len(tool_durations) if tool_durations else None,
            average_handoff_resolution_ms=sum(handoff_durations) / len(handoff_durations) if handoff_durations else None,
        ),
        alerts=alerts,
        versions=versions,
    )
class QualityService:
    def __init__(self, unit_of_work: SqliteUnitOfWork) -> None:
        self._unit = unit_of_work

    def overview(self, range_name: str = "24h") -> QualityOverview:
        cutoff = _range_cutoff(range_name)
        runs = [
            run
            for run in self._unit.agent_runs.list_all()
            if cutoff is None or run.started_at >= cutoff
        ]
        run_ids = {run.run_id for run in runs}
        steps = [
            step for step in self._unit.agent_run_steps.list_all()
            if step.run_id in run_ids
        ]
        return aggregate_quality(runs, steps)

    def trends(self, range_name: str = "7d") -> list[QualityTrendPoint]:
        cutoff = _range_cutoff(range_name)
        runs = [
            run
            for run in self._unit.agent_runs.list_all()
            if cutoff is None or run.started_at >= cutoff
        ]
        grouped: dict[str, list[AgentRunRecord]] = {}
        for run in runs:
            key = run.started_at.astimezone(timezone.utc).date().isoformat()
            grouped.setdefault(key, []).append(run)

        points: list[QualityTrendPoint] = []
        for date, date_runs in sorted(grouped.items()):
            metrics = aggregate_quality(date_runs, [])
            points.append(
                QualityTrendPoint(
                    date=date,
                    total_runs=metrics.total_runs,
                    successful_runs=metrics.successful_runs,
                    failed_runs=metrics.failed_runs,
                    waiting_confirmation_runs=metrics.waiting_confirmation_runs,
                    success_rate=metrics.success_rate,
                    average_duration_ms=metrics.average_duration_ms,
                    total_tokens=metrics.total_tokens,
                    token_usage_available=metrics.token_usage_available,
                    total_estimated_cost_cny=metrics.total_estimated_cost_cny,
                    cost_available=metrics.cost_available,
                )
            )
        return points

    def operations(self, range_name: str = "24h") -> OperationsOverview:
        cutoff = _range_cutoff(range_name)
        runs = [run for run in self._unit.agent_runs.list_all() if cutoff is None or run.started_at >= cutoff]
        run_ids = {run.run_id for run in runs}
        steps = [step for step in self._unit.agent_run_steps.list_all() if step.run_id in run_ids]
        handoffs = [item for item in self._unit.human_handoffs.list() if cutoff is None or item.created_at >= cutoff]
        return aggregate_operations(runs, steps, handoffs)

    def list_runs(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        source: str | None = None,
        status: str | None = None,
        planner_type: str | None = None,
    ) -> RunPage:
        items = self._unit.agent_runs.list_all()
        if source:
            items = [item for item in items if item.source == source]
        if status:
            items = [item for item in items if item.status == status]
        if planner_type:
            items = [item for item in items if item.planner_type == planner_type]
        total = len(items)
        return RunPage(items=items[offset:offset + min(limit, 100)], total=total)

    def get_run(self, run_id: str) -> RunDetail:
        run = self._unit.agent_runs.get(run_id)
        if run is None:
            raise KeyError(run_id)
        steps = self._unit.agent_run_steps.list_for_run(run_id)
        evidence: dict[str, PolicyEvidence] = {}
        for step in steps:
            if step.name not in {"rag.completed", "rag.degraded"}:
                continue
            for hit in step.summary.get("hits") or []:
                policy_id = str(hit.get("policy_id") or "")
                if policy_id:
                    evidence[policy_id] = PolicyEvidence(
                        policy_id=policy_id,
                        title=str(hit.get("title") or ""),
                        source_url=str(hit.get("source_url") or ""),
                    )
        business_outcome = (
            "succeeded" if run.business_success is True
            else "failed" if run.business_success is False
            else "pending_confirmation" if run.status == "waiting_confirmation"
            else "not_verified"
        )
        return RunDetail(
            run=run,
            steps=steps,
            policy_evidence=list(evidence.values()),
            business_outcome=business_outcome,
        )


def _range_cutoff(range_name: str) -> datetime | None:
    now = datetime.now(timezone.utc)
    durations = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}
    if range_name == "all":
        return None
    if range_name not in durations:
        raise ValueError(range_name)
    return now - durations[range_name]
