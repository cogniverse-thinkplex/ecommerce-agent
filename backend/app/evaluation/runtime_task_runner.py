from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from re import sub
from typing import Literal

from pydantic import BaseModel, Field

from app.agent.trace import TraceEntry, build_session_trace
from app.agent.runtime import AgentAutoRunResult
from app.agent.proposal_generator import (
    LLMProposalGenerator,
    LiteLLMClient,
    RuleBasedProposalGenerator,
)
from app.agent.runtime import LLMPlannerRuntime
from app.agent.session_service import AgentSessionService
from app.agent.nodes.tool_node import ToolCallRequest
from app.agent.skills import default_skill_registry
from app.evaluation.session_task_check import SessionTaskCheck, compare_session_to_task
from app.evaluation.outcome_evaluator import with_execution_evidence
from app.policy.guard import fingerprint_action
from app.evaluation.tau_retail_tasks import RetailTaskSummary, load_retail_task_summary
from app.tools.guarded_executor import GuardedRetailToolExecutor
from app.tools.tau_retail_adapter import TauRetailAdapter

RuntimePlannerType = Literal["rule", "llm"]


class RuntimeTaskRunResult(BaseModel):
    task_id: str
    planner_type: RuntimePlannerType = "rule"
    conversation_id: str
    step_budget: int = 6
    step_count: int = 0
    cost: float | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_list_cost_cny: float | None = None
    llm_usage_available: bool = False
    llm_usage_requests: list[dict] = Field(default_factory=list)
    outcome_verification_mode: Literal["confirmation_gate", "confirmed_state"] = (
        "confirmation_gate"
    )
    stopped_reason: str
    check: SessionTaskCheck
    diagnostic: "RuntimeTaskDiagnostic"
    failure_summary: "RuntimeFailureSummary"
    trace_entries: list[TraceEntry] = Field(default_factory=list)
    action_timeline: list["RuntimeActionTimelineItem"] = Field(default_factory=list)


class RuntimeTaskDiagnostic(BaseModel):
    first_mismatch_index: int | None
    expected_action: str | None
    actual_action: str | None
    message: str


class RuntimeActionTimelineItem(BaseModel):
    index: int
    expected_action: str | None
    actual_action: str | None
    matched: bool
    trace_sequence: int | None = None
    trace_kind: str | None = None
    rationale: str | None = None
    rejection_reason: str | None = None


class RuntimeFailureSummary(BaseModel):
    category: str
    recommended_action: str
    rejection_kind: str | None = None
    rejection_reason: str | None = None
    planner_terminal_kind: str | None = None
    planner_message: str | None = None
    first_mismatch_index: int | None = None
    recovery_kinds: list[str] = Field(default_factory=list)


class RuntimeSubsetSummary(BaseModel):
    total_tasks: int = 0
    exact_match_count: int = 0
    business_success_count: int = 0
    confirmation_gate_success_count: int = 0
    confirmed_outcome_success_count: int = 0
    exact_match_rate: float = 0.0
    business_success_rate: float = 0.0
    confirmation_gate_success_rate: float = 0.0
    confirmed_outcome_success_rate: float = 0.0
    average_step_count: float = 0.0
    cost_available: bool = False
    total_cost: float | None = None
    average_cost: float | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_list_cost_cny_available: bool = False
    total_estimated_list_cost_cny: float | None = None
    average_estimated_list_cost_cny: float | None = None
    scenario_metrics: dict[str, "RuntimeScenarioMetrics"] = Field(default_factory=dict)
    failed_task_ids: list[str] = Field(default_factory=list)
    business_failed_task_ids: list[str] = Field(default_factory=list)
    deviation_task_ids: list[str] = Field(default_factory=list)
    stopped_reasons: dict[str, int] = Field(default_factory=dict)


class RuntimeSubsetArtifact(BaseModel):
    run_name: str
    planner_type: RuntimePlannerType = "rule"
    path: str
    created_at: datetime
    task_ids: list[str]
    max_steps: int
    task_step_budgets: dict[str, int] = Field(default_factory=dict)
    task_scenarios: dict[str, str] = Field(default_factory=dict)
    summary: RuntimeSubsetSummary = Field(default_factory=RuntimeSubsetSummary)
    results: list[RuntimeTaskRunResult]


class RuntimeScenarioMetrics(BaseModel):
    task_count: int = 0
    business_success_rate: float = 0.0
    confirmation_gate_success_rate: float = 0.0
    confirmed_outcome_success_rate: float = 0.0
    exact_match_rate: float = 0.0
    average_step_count: float = 0.0
    cost_available: bool = False
    total_cost: float | None = None
    average_cost: float | None = None


class ConfirmedWriteRunResult(BaseModel):
    state: object
    auto_run: AgentAutoRunResult
    executed_write_count: int = 0
    before_hash: str | None = None
    after_hash: str | None = None


def run_retail_task_subset(
    task_ids: list[str],
    *,
    split: str | None = "base",
    max_steps: int = 6,
    task_step_budgets: dict[str, int] | None = None,
    planner_type: RuntimePlannerType = "rule",
    verify_outcome_execution: bool = False,
) -> list[RuntimeTaskRunResult]:
    results: list[RuntimeTaskRunResult] = []
    for task_id in task_ids:
        task = load_retail_task_summary(task_id, split=split)
        conversation_id = f"retail-task-{task.task_id}"
        service = _build_session_service(planner_type)
        service.start_session(conversation_id)
        step_budget = (task_step_budgets or {}).get(task.task_id, max_steps)
        objective = _build_task_prompt(task)
        confirmed_run = None
        if verify_outcome_execution:
            confirmed_run = _run_with_confirmed_writes(
                service,
                conversation_id=conversation_id,
                objective=objective,
                task=task,
                max_steps=step_budget,
            )
            auto_run = confirmed_run.auto_run
        else:
            auto_run = service.auto_run(
                conversation_id,
                objective,
                max_steps=step_budget,
            )
        check = compare_session_to_task(auto_run.state, task)
        if verify_outcome_execution:
            outcome = check.outcome
            if outcome is not None and outcome.confirmation_executed:
                state_changed = (
                    confirmed_run.before_hash != confirmed_run.after_hash
                    if confirmed_run is not None
                    and confirmed_run.before_hash is not None
                    and confirmed_run.after_hash is not None
                    else None
                )
                verified = with_execution_evidence(
                    outcome,
                    executed=True,
                    tool_error=False,
                    state_changed=state_changed,
                )
                check = check.model_copy(
                    update={
                        "outcome": verified,
                        "business_success": verified.success,
                        "confirmation_gate_success": outcome.confirmation_gate_reached,
                        "confirmed_outcome_success": verified.success,
                        "business_success_basis": (
                            "confirmed_state_change" if verified.success else "none"
                        ),
                    }
                )
        trace = service.get_trace(conversation_id)
        usage = _planner_usage(service)
        diagnostic = diagnose_session_task_check(check)
        results.append(
            RuntimeTaskRunResult(
                task_id=task.task_id,
                planner_type=planner_type,
                conversation_id=conversation_id,
                step_budget=step_budget,
                step_count=len(check.actual_actions),
                cost=0.0 if planner_type == "rule" else None,
                prompt_tokens=usage["prompt_tokens"],
                completion_tokens=usage["completion_tokens"],
                total_tokens=usage["total_tokens"],
                estimated_list_cost_cny=usage["estimated_list_cost_cny"],
                llm_usage_available=bool(usage["usage_available"]),
                llm_usage_requests=usage["usage_requests"],
                outcome_verification_mode=(
                    "confirmed_state"
                    if verify_outcome_execution
                    else "confirmation_gate"
                ),
                stopped_reason=auto_run.stopped_reason,
                check=check,
                diagnostic=diagnostic,
                failure_summary=_summarize_failure(
                    stopped_reason=auto_run.stopped_reason,
                    diagnostic=diagnostic,
                    trace_entries=trace.entries,
                    business_success=check.business_success,
                    confirmation_executed=bool(
                        check.outcome and check.outcome.confirmation_executed
                    ),
                ),
                trace_entries=_compact_trace_entries(trace.entries),
                action_timeline=_build_action_timeline(check, trace.entries),
            )
        )
    return results


def _run_with_confirmed_writes(
    service: AgentSessionService,
    *,
    conversation_id: str,
    objective: str,
    task: RetailTaskSummary,
    max_steps: int,
) -> ConfirmedWriteRunResult:
    expected_writes = [
        action
        for action in task.expected_actions
        if action.name
        in {
            "cancel_pending_order",
            "exchange_delivered_order_items",
            "modify_pending_order_address",
            "modify_pending_order_items",
            "modify_pending_order_payment",
            "modify_user_address",
            "return_delivered_order_items",
        }
    ]
    before_hash = service.backend_state_hash()
    auto_run = service.auto_run(
        conversation_id,
        objective,
        max_steps=max_steps,
    )
    used_steps = len(auto_run.turns)
    executed_count = 0

    for _ in expected_writes:
        pending = auto_run.state.confirmation.pending
        if pending is None:
            break
        if not any(
            pending.name == action.name and pending.arguments == action.arguments
            for action in expected_writes
        ):
            break
        remaining_steps = max_steps - used_steps
        if remaining_steps <= 0:
            break
        is_last_expected_write = executed_count + 1 == len(expected_writes)
        if is_last_expected_write:
            service.apply_confirmation_reply(
                conversation_id,
                confirmed=True,
                user_text="confirm from outcome evaluator",
            )
            executed = service.apply_tool_request(
                conversation_id,
                ToolCallRequest(
                    name=pending.name,
                    arguments=pending.arguments,
                    call_id=f"outcome-{task.task_id}-{executed_count}",
                ),
            )
            if not executed.executed or executed.error:
                break
            executed_count += 1
            auto_run = AgentAutoRunResult(
                state=executed.state,
                turns=auto_run.turns,
                stopped_reason="no_proposal",
            )
            break

        continued = service.confirm_pending_and_continue(
            conversation_id,
            confirmed=True,
            user_text="confirm from outcome evaluator",
            objective=objective,
            max_steps=remaining_steps,
        )
        if continued.executed is None or not continued.executed.executed:
            break
        executed_count += 1
        if continued.auto_run is None:
            break
        auto_run = continued.auto_run
        used_steps += len(auto_run.turns)

    return ConfirmedWriteRunResult(
        state=auto_run.state,
        auto_run=auto_run,
        executed_write_count=executed_count,
        before_hash=before_hash,
        after_hash=service.backend_state_hash(),
    )


def _verify_outcome_execution(
    service: AgentSessionService,
    *,
    conversation_id: str,
    check: SessionTaskCheck,
) -> SessionTaskCheck:
    outcome = check.outcome
    state = service.get_session(conversation_id)
    pending = state.confirmation.pending
    if outcome is None or not outcome.success or pending is None:
        return check
    expected_fingerprint = fingerprint_action(
        outcome.target_action or "",
        outcome.expected_arguments,
    )
    if (
        pending.name != outcome.target_action
        or pending.arguments != outcome.expected_arguments
        or pending.fingerprint != expected_fingerprint
    ):
        return check

    before_hash = service.backend_state_hash()
    service.apply_confirmation_reply(
        conversation_id,
        confirmed=True,
        user_text="confirm from outcome evaluator",
    )
    execution = service.apply_tool_request(
        conversation_id,
        ToolCallRequest(
            name=pending.name,
            arguments=pending.arguments,
            call_id=f"outcome-{check.task_id}",
        ),
    )
    after_hash = service.backend_state_hash()
    state_changed = (
        before_hash != after_hash
        if before_hash is not None and after_hash is not None
        else None
    )
    executed_event = next(
        (
            event
            for event in reversed(execution.state.events)
            if event.event_type == "tool_executor.executed"
        ),
        None,
    )
    tool_error = bool(
        execution.error
        or executed_event is None
        or executed_event.payload.get("error")
    )
    verified = with_execution_evidence(
        outcome,
        executed=execution.executed,
        tool_error=tool_error,
        state_changed=state_changed,
    )
    return check.model_copy(
        update={
            "outcome": verified,
            "business_success": verified.success,
            "confirmation_gate_success": check.confirmation_gate_success,
            "confirmed_outcome_success": verified.success,
            "business_success_basis": (
                "confirmed_state_change" if verified.success else "none"
            ),
        }
    )


def save_runtime_task_subset_artifact(
    results: list[RuntimeTaskRunResult],
    *,
    output_dir: Path,
    run_name: str | None = None,
    max_steps: int,
    task_step_budgets: dict[str, int] | None = None,
    task_scenarios: dict[str, str] | None = None,
) -> RuntimeSubsetArtifact:
    safe_run_name = _safe_run_name(run_name) if run_name else _default_run_name()
    run_dir = output_dir / safe_run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    artifact_file = run_dir / "runtime_subset.json"
    artifact = RuntimeSubsetArtifact(
        run_name=safe_run_name,
        planner_type=results[0].planner_type if results else "rule",
        path=str(artifact_file),
        created_at=datetime.now(UTC),
        task_ids=[result.task_id for result in results],
        max_steps=max_steps,
        task_step_budgets=task_step_budgets or {},
        task_scenarios=task_scenarios or {},
        summary=_summarize_runtime_subset_results(
            results,
            task_scenarios=task_scenarios,
        ),
        results=results,
    )
    artifact_file.write_text(
        json.dumps(artifact.model_dump(mode="json"), ensure_ascii=False, indent=2)
    )
    return artifact


def _build_session_service(planner_type: RuntimePlannerType) -> AgentSessionService:
    executor = GuardedRetailToolExecutor(TauRetailAdapter.from_default_data())
    if planner_type == "llm":
        skill_registry = default_skill_registry()
        proposal_generator = LLMProposalGenerator(
            model=os.getenv("ECOM_AGENT_PROPOSAL_LLM", "dashscope/deepseek-v4-pro-0813"),
            client=LiteLLMClient(),
            tool_catalog=executor.list_tools(),
            skill_registry=skill_registry.list(),
            policy=executor.policy,
        )
        return AgentSessionService(
            executor,
            runtime=LLMPlannerRuntime(
                executor,
                proposal_generator,
                skill_registry=skill_registry,
            ),
        )
    return AgentSessionService(
        executor,
        proposal_generator=RuleBasedProposalGenerator(),
    )


def _planner_usage(service: AgentSessionService) -> dict:
    generator = service.proposal_generator
    client = getattr(generator, "client", None)
    return {
        "prompt_tokens": int(getattr(client, "prompt_tokens", 0)),
        "completion_tokens": int(getattr(client, "completion_tokens", 0)),
        "total_tokens": int(getattr(client, "total_tokens", 0)),
        "estimated_list_cost_cny": getattr(
            client,
            "estimated_list_cost_cny",
            None,
        ),
        "usage_available": bool(getattr(client, "usage_available", False)),
        "usage_requests": list(getattr(client, "usage_requests", [])),
    }


def load_runtime_task_subset_artifact(
    output_dir: Path,
    run_name: str,
) -> RuntimeSubsetArtifact:
    artifact_file = output_dir / run_name / "runtime_subset.json"
    if not artifact_file.exists():
        raise KeyError(f"Runtime subset artifact not found: {run_name}")
    return RuntimeSubsetArtifact.model_validate_json(artifact_file.read_text())


def _summarize_runtime_subset_results(
    results: list[RuntimeTaskRunResult],
    *,
    task_scenarios: dict[str, str] | None = None,
) -> RuntimeSubsetSummary:
    stopped_reasons: dict[str, int] = {}
    failed_task_ids: list[str] = []
    deviation_task_ids: list[str] = []
    exact_match_count = 0
    business_success_count = 0
    confirmation_gate_success_count = 0
    confirmed_outcome_success_count = 0
    business_failed_task_ids: list[str] = []
    for result in results:
        stopped_reasons[result.stopped_reason] = (
            stopped_reasons.get(result.stopped_reason, 0) + 1
        )
        if result.check.exact_match:
            exact_match_count += 1
        result_succeeded = (
            result.check.confirmed_outcome_success
            if result.outcome_verification_mode == "confirmed_state"
            else result.check.confirmation_gate_success
        )
        if not result_succeeded:
            failed_task_ids.append(result.task_id)
        if result.check.business_success:
            business_success_count += 1
        else:
            business_failed_task_ids.append(result.task_id)
        if result.check.confirmation_gate_success:
            confirmation_gate_success_count += 1
        if result.check.confirmed_outcome_success:
            confirmed_outcome_success_count += 1
        if result.diagnostic.first_mismatch_index is not None:
            deviation_task_ids.append(result.task_id)
    count = len(results)
    cost_available = bool(results) and all(result.cost is not None for result in results)
    total_cost = (
        sum(float(result.cost) for result in results if result.cost is not None)
        if cost_available
        else None
    )
    estimated_cost_available = bool(results) and all(
        result.estimated_list_cost_cny is not None for result in results
    )
    total_estimated_cost = (
        sum(
            float(result.estimated_list_cost_cny)
            for result in results
            if result.estimated_list_cost_cny is not None
        )
        if estimated_cost_available
        else None
    )
    return RuntimeSubsetSummary(
        total_tasks=len(results),
        exact_match_count=exact_match_count,
        business_success_count=business_success_count,
        confirmation_gate_success_count=confirmation_gate_success_count,
        confirmed_outcome_success_count=confirmed_outcome_success_count,
        exact_match_rate=exact_match_count / count if count else 0.0,
        business_success_rate=business_success_count / count if count else 0.0,
        confirmation_gate_success_rate=(
            confirmation_gate_success_count / count if count else 0.0
        ),
        confirmed_outcome_success_rate=(
            confirmed_outcome_success_count / count if count else 0.0
        ),
        average_step_count=(
            sum(result.step_count for result in results) / count if count else 0.0
        ),
        cost_available=cost_available,
        total_cost=total_cost,
        average_cost=(total_cost / count if total_cost is not None and count else None),
        prompt_tokens=sum(result.prompt_tokens for result in results),
        completion_tokens=sum(result.completion_tokens for result in results),
        total_tokens=sum(result.total_tokens for result in results),
        estimated_list_cost_cny_available=estimated_cost_available,
        total_estimated_list_cost_cny=total_estimated_cost,
        average_estimated_list_cost_cny=(
            total_estimated_cost / count
            if total_estimated_cost is not None and count
            else None
        ),
        scenario_metrics=_scenario_metrics(results, task_scenarios or {}),
        failed_task_ids=failed_task_ids,
        business_failed_task_ids=business_failed_task_ids,
        deviation_task_ids=deviation_task_ids,
        stopped_reasons=stopped_reasons,
    )


def _scenario_metrics(
    results: list[RuntimeTaskRunResult],
    task_scenarios: dict[str, str],
) -> dict[str, RuntimeScenarioMetrics]:
    grouped: dict[str, list[RuntimeTaskRunResult]] = {}
    for result in results:
        scenario = task_scenarios.get(result.task_id)
        if scenario is not None:
            grouped.setdefault(scenario, []).append(result)
    metrics: dict[str, RuntimeScenarioMetrics] = {}
    for scenario, scenario_results in grouped.items():
        count = len(scenario_results)
        cost_available = all(result.cost is not None for result in scenario_results)
        total_cost = (
            sum(
                float(result.cost)
                for result in scenario_results
                if result.cost is not None
            )
            if cost_available
            else None
        )
        metrics[scenario] = RuntimeScenarioMetrics(
            task_count=count,
            business_success_rate=(
                sum(result.check.business_success for result in scenario_results) / count
            ),
            confirmation_gate_success_rate=(
                sum(
                    result.check.confirmation_gate_success
                    for result in scenario_results
                )
                / count
            ),
            confirmed_outcome_success_rate=(
                sum(
                    result.check.confirmed_outcome_success
                    for result in scenario_results
                )
                / count
            ),
            exact_match_rate=(
                sum(result.check.exact_match for result in scenario_results) / count
            ),
            average_step_count=(
                sum(result.step_count for result in scenario_results) / count
            ),
            cost_available=cost_available,
            total_cost=total_cost,
            average_cost=total_cost / count if total_cost is not None else None,
        )
    return metrics


def _build_task_prompt(task: RetailTaskSummary) -> str:
    return (
        f"{task.known_info}\n"
        f"{task.reason_for_call}\n"
        f"{task.task_instructions}"
    )


def _summarize_failure(
    *,
    stopped_reason: str,
    diagnostic: RuntimeTaskDiagnostic,
    trace_entries: list[TraceEntry],
    business_success: bool = False,
    confirmation_executed: bool = False,
) -> RuntimeFailureSummary:
    recovery_entries = [
        entry
        for entry in trace_entries
        if entry.source == "event" and entry.kind in _RECOVERY_EVENT_KINDS
    ]
    recovery_kinds = list(dict.fromkeys(entry.kind for entry in recovery_entries))
    if business_success and confirmation_executed:
        return RuntimeFailureSummary(
            category="business_success",
            recommended_action="目标写操作已确认执行并验证状态变化，无需按失败处理。",
            first_mismatch_index=diagnostic.first_mismatch_index,
            recovery_kinds=recovery_kinds,
        )
    if diagnostic.first_mismatch_index is None and stopped_reason == "pending_confirmation":
        return RuntimeFailureSummary(
            category="pending_confirmation",
            recommended_action="目标写操作已到达确认门禁，但尚未执行；确认或拒绝后才能判断落库结果。",
            recovery_kinds=recovery_kinds,
        )
    if business_success and stopped_reason == "pending_confirmation":
        return RuntimeFailureSummary(
            category="confirmation_gate_success",
            recommended_action="目标写操作和参数已通过确认门禁；保留动作偏差用于轨迹审计，尚未验证落库。",
            first_mismatch_index=diagnostic.first_mismatch_index,
            recovery_kinds=recovery_kinds,
        )

    rejection = next(
        (
            entry
            for entry in reversed(trace_entries)
            if entry.source == "event" and entry.kind.endswith(".rejected")
            and not any(recovery.sequence > entry.sequence for recovery in recovery_entries)
        ),
        None,
    )
    planner_terminal = next(
        (
            entry
            for entry in reversed(trace_entries)
            if entry.kind
            in {
                "planner.final_response",
                "planner.need_more_info",
                "planner.invalid_output",
            }
        ),
        None,
    )
    if rejection is not None:
        return RuntimeFailureSummary(
            category="rejected",
            recommended_action="查看被拒绝事件的 reason，并检查 skill/action、tool schema 或 policy 配置。",
            rejection_kind=rejection.kind,
            rejection_reason=_payload_text(rejection.payload, "reason", "message", "error"),
            first_mismatch_index=diagnostic.first_mismatch_index,
            recovery_kinds=recovery_kinds,
        )
    if planner_terminal is not None:
        return RuntimeFailureSummary(
            category="planner_terminal",
            recommended_action="检查 planner 是否过早结束、请求更多信息，或输出了无效 JSON。",
            planner_terminal_kind=planner_terminal.kind,
            planner_message=_payload_text(
                planner_terminal.payload,
                "message",
                "content",
                "error",
            ),
            first_mismatch_index=diagnostic.first_mismatch_index,
            recovery_kinds=recovery_kinds,
        )
    if diagnostic.first_mismatch_index is not None:
        return RuntimeFailureSummary(
            category="action_deviation",
            recommended_action="对照第一处偏差和动作时间线，检查 skill routing 或 planner tool selection。",
            first_mismatch_index=diagnostic.first_mismatch_index,
            recovery_kinds=recovery_kinds,
        )
    if stopped_reason == "max_steps":
        return RuntimeFailureSummary(
            category="max_steps",
            recommended_action="检查是否循环、缺少终止条件，或适当提高 max_steps 后复测。",
            recovery_kinds=recovery_kinds,
        )
    return RuntimeFailureSummary(
        category="success",
        recommended_action="暂无需要排查的失败原因。",
        recovery_kinds=recovery_kinds,
    )


_RECOVERY_EVENT_KINDS = {
    "planner.terminal_fallback",
    "planner.repeated_read_fallback",
    "planner.known_product_fallback",
    "planner.rejected_tool_fallback",
    "planner.rejected_tool_repair",
    "planner.rejected_skill_fallback",
    "planner.invalid_skill_metadata_removed",
}


def _payload_text(payload: dict[str, object], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value:
            return str(value)
    return None


def diagnose_session_task_check(check: SessionTaskCheck) -> RuntimeTaskDiagnostic:
    if check.exact_match:
        return RuntimeTaskDiagnostic(
            first_mismatch_index=None,
            expected_action=None,
            actual_action=None,
            message="动作序列完全匹配。",
        )
    index = check.matched_prefix_count
    expected_action = (
        check.expected_actions[index] if index < len(check.expected_actions) else None
    )
    actual_action = check.actual_actions[index] if index < len(check.actual_actions) else None
    if actual_action is None and expected_action is not None:
        message = f"第 {index + 1} 个动作缺失，预期执行 {expected_action}。"
    elif expected_action is None and actual_action is not None:
        message = f"第 {index + 1} 个动作是额外动作 {actual_action}。"
    else:
        message = (
            f"第 {index + 1} 个动作不匹配，预期 {expected_action}，实际 {actual_action}。"
        )
    return RuntimeTaskDiagnostic(
        first_mismatch_index=index,
        expected_action=expected_action,
        actual_action=actual_action,
        message=message,
    )


def _compact_trace_entries(entries: list[TraceEntry]) -> list[TraceEntry]:
    return [
        entry
        for entry in entries
        if entry.source == "event"
        or entry.kind in {"user", "assistant", "tool"}
    ]


def _build_action_timeline(
    check: SessionTaskCheck,
    trace_entries: list[TraceEntry],
) -> list[RuntimeActionTimelineItem]:
    action_events = [
        entry
        for entry in trace_entries
        if entry.kind == "tool_proposal.accepted" and entry.payload.get("tool")
    ]
    rejection_events = [
        entry
        for entry in trace_entries
        if entry.source == "event" and entry.kind.endswith(".rejected")
    ]
    length = max(len(check.expected_actions), len(check.actual_actions))
    timeline: list[RuntimeActionTimelineItem] = []
    for index in range(length):
        expected_action = (
            check.expected_actions[index] if index < len(check.expected_actions) else None
        )
        actual_action = (
            check.actual_actions[index] if index < len(check.actual_actions) else None
        )
        event = action_events[index] if index < len(action_events) else None
        rejection = rejection_events[index] if index < len(rejection_events) else None
        timeline.append(
            RuntimeActionTimelineItem(
                index=index,
                expected_action=expected_action,
                actual_action=actual_action,
                matched=expected_action == actual_action,
                trace_sequence=event.sequence if event is not None else None,
                trace_kind=event.kind if event is not None else None,
                rationale=(
                    str(event.payload.get("rationale"))
                    if event is not None and event.payload.get("rationale")
                    else None
                ),
                rejection_reason=(
                    str(rejection.payload.get("reason"))
                    if rejection is not None and rejection.payload.get("reason")
                    else None
                ),
            )
        )
    return timeline


def _safe_run_name(run_name: str) -> str:
    safe = sub(r"[^A-Za-z0-9_.-]+", "-", run_name.strip()).strip(".-")
    return safe or _default_run_name()


def _default_run_name() -> str:
    return f"runtime-subset-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
