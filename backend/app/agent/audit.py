from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agent.state import AgentEvent, CustomerAgentState, WriteObjective


ConfirmationStatus = Literal["not_requested", "pending", "confirmed", "rejected"]
ExecutionStatus = Literal["not_executed", "pending", "succeeded", "failed"]
StateVerification = Literal["not_run", "unavailable", "unchanged", "changed"]


class AuditObjective(BaseModel):
    objective_id: str
    tool_name: str
    order_id: str | None = None
    intent: str = ""
    plan_status: Literal["pending", "completed"] = "pending"
    fingerprint: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    confirmation_status: ConfirmationStatus = "not_requested"
    execution_status: ExecutionStatus = "not_executed"
    state_verification: StateVerification = "not_run"


class AuditTimelineEntry(BaseModel):
    sequence: int
    kind: Literal["confirmation_requested", "confirmed", "rejected", "executed"]
    created_at: datetime
    tool_name: str
    fingerprint: str | None = None
    error: bool | None = None
    state_verification: StateVerification = "not_run"


class AuditSummary(BaseModel):
    total_objectives: int
    completed_objectives: int
    pending_objectives: int
    rejected_objectives: int
    verified_state_changes: int


class SessionAudit(BaseModel):
    conversation_id: str
    original_objective: str = ""
    summary: AuditSummary
    objectives: list[AuditObjective] = Field(default_factory=list)
    timeline: list[AuditTimelineEntry] = Field(default_factory=list)


def build_session_audit(state: CustomerAgentState) -> SessionAudit:
    relevant_events = [
        event
        for event in state.events
        if event.event_type
        in {
            "policy_guard.requires_confirmation",
            "policy_guard.confirmed",
            "policy_guard.rejected",
            "tool_executor.executed",
        }
        and event.payload.get("tool")
    ]
    objectives = [_build_objective(state, item, relevant_events) for item in state.objective_ledger.write_plan]

    known_fingerprints = {item.fingerprint for item in objectives if item.fingerprint}
    for index, completed in enumerate(state.objective_ledger.completed_writes, start=1):
        if completed.fingerprint in known_fingerprints:
            continue
        synthetic = WriteObjective(
            objective_id=f"completed-{index}",
            tool_name=completed.name,
            order_id=_order_id(completed.arguments),
            status="completed",
            completed_fingerprint=completed.fingerprint,
        )
        objectives.append(_build_objective(state, synthetic, relevant_events))
        known_fingerprints.add(completed.fingerprint)

    requested_events = [
        event
        for event in relevant_events
        if event.event_type == "policy_guard.requires_confirmation"
        and event.payload.get("fingerprint")
    ]
    for index, event in enumerate(requested_events, start=1):
        fingerprint = str(event.payload["fingerprint"])
        if fingerprint in known_fingerprints:
            continue
        arguments = event.payload.get("arguments")
        arguments = arguments if isinstance(arguments, dict) else {}
        synthetic = WriteObjective(
            objective_id=f"audit-{index}",
            tool_name=str(event.payload["tool"]),
            order_id=_order_id(arguments),
        )
        objectives.append(_build_objective(state, synthetic, relevant_events))
        known_fingerprints.add(fingerprint)

    pending = state.confirmation.pending
    if pending is not None and pending.fingerprint not in known_fingerprints:
        synthetic = WriteObjective(
            objective_id="pending-confirmation",
            tool_name=pending.name,
            order_id=_order_id(pending.arguments),
        )
        objectives.append(_build_objective(state, synthetic, relevant_events))

    timeline = [
        _timeline_entry(sequence, event)
        for sequence, event in enumerate(relevant_events, start=1)
    ]
    return SessionAudit(
        conversation_id=state.conversation_id,
        original_objective=state.objective_ledger.original_objective,
        summary=AuditSummary(
            total_objectives=len(objectives),
            completed_objectives=sum(item.plan_status == "completed" for item in objectives),
            pending_objectives=sum(item.plan_status == "pending" for item in objectives),
            rejected_objectives=sum(item.confirmation_status == "rejected" for item in objectives),
            verified_state_changes=sum(item.state_verification == "changed" for item in objectives),
        ),
        objectives=objectives,
        timeline=timeline,
    )


def _build_objective(
    state: CustomerAgentState,
    objective: WriteObjective,
    events: list[AgentEvent],
) -> AuditObjective:
    completed = next(
        (
            item
            for item in state.objective_ledger.completed_writes
            if item.fingerprint == objective.completed_fingerprint
        ),
        None,
    )
    matching_events = [
        event
        for event in events
        if event.payload.get("tool") == objective.tool_name
        and _event_matches_objective(event, objective)
    ]
    fingerprint = objective.completed_fingerprint or _latest_fingerprint(matching_events)
    if fingerprint:
        matching_events = [
            event for event in matching_events if event.payload.get("fingerprint") == fingerprint
        ]
    requested = _latest_event(matching_events, "policy_guard.requires_confirmation")
    confirmed = _latest_event(matching_events, "policy_guard.confirmed")
    rejected = _latest_event(matching_events, "policy_guard.rejected")
    executed = _latest_event(matching_events, "tool_executor.executed")

    confirmation_status: ConfirmationStatus = "not_requested"
    if rejected is not None:
        confirmation_status = "rejected"
    elif confirmed is not None:
        confirmation_status = "confirmed"
    elif requested is not None:
        confirmation_status = "pending"

    execution_status: ExecutionStatus = "not_executed"
    if executed is not None:
        execution_status = "failed" if executed.payload.get("error") else "succeeded"
    elif confirmation_status == "pending":
        execution_status = "pending"

    arguments = completed.arguments if completed is not None else {}
    if not arguments and requested is not None:
        raw_arguments = requested.payload.get("arguments")
        arguments = raw_arguments if isinstance(raw_arguments, dict) else {}

    return AuditObjective(
        objective_id=objective.objective_id,
        tool_name=objective.tool_name,
        order_id=objective.order_id,
        intent=objective.intent,
        plan_status=objective.status,
        fingerprint=fingerprint,
        arguments=arguments,
        confirmation_status=confirmation_status,
        execution_status=execution_status,
        state_verification=_state_verification(executed),
    )


def _event_matches_objective(event: AgentEvent, objective: WriteObjective) -> bool:
    if objective.completed_fingerprint:
        return event.payload.get("fingerprint") == objective.completed_fingerprint
    arguments = event.payload.get("arguments")
    if not objective.order_id or not isinstance(arguments, dict):
        return True
    return _order_id(arguments) == objective.order_id


def _latest_event(events: list[AgentEvent], event_type: str) -> AgentEvent | None:
    return next((event for event in reversed(events) if event.event_type == event_type), None)


def _latest_fingerprint(events: list[AgentEvent]) -> str | None:
    return next(
        (
            str(event.payload["fingerprint"])
            for event in reversed(events)
            if event.payload.get("fingerprint")
        ),
        None,
    )


def _state_verification(event: AgentEvent | None) -> StateVerification:
    if event is None:
        return "not_run"
    if not event.payload.get("state_verification_available"):
        return "unavailable"
    return "changed" if event.payload.get("state_changed") else "unchanged"


def _timeline_entry(sequence: int, event: AgentEvent) -> AuditTimelineEntry:
    kind_map = {
        "policy_guard.requires_confirmation": "confirmation_requested",
        "policy_guard.confirmed": "confirmed",
        "policy_guard.rejected": "rejected",
        "tool_executor.executed": "executed",
    }
    return AuditTimelineEntry(
        sequence=sequence,
        kind=kind_map[event.event_type],
        created_at=event.created_at,
        tool_name=str(event.payload["tool"]),
        fingerprint=(str(event.payload["fingerprint"]) if event.payload.get("fingerprint") else None),
        error=(bool(event.payload.get("error")) if event.event_type == "tool_executor.executed" else None),
        state_verification=_state_verification(event),
    )


def _order_id(arguments: dict[str, Any]) -> str | None:
    value = arguments.get("order_id")
    return str(value) if value is not None else None
