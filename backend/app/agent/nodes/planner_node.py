from __future__ import annotations

from app.agent.proposal_generator import PlannerDecision
from app.agent.response_quality import append_response_quality_event
from app.agent.state import ConversationMessage, CustomerAgentState, append_event


def apply_planner_decision(
    state: CustomerAgentState,
    decision: PlannerDecision,
) -> CustomerAgentState | None:
    if decision.action == "invalid":
        return append_event(
            state,
            "planner.invalid_output",
            {"error": decision.error or "Invalid planner output"},
        )
    if decision.action == "final_response":
        return _append_planner_message(
            state,
            event_type="planner.final_response",
            message=decision.message,
            rationale=decision.rationale,
        )
    if decision.action == "need_more_info":
        return _append_planner_message(
            state,
            event_type="planner.need_more_info",
            message=decision.message,
            rationale=decision.rationale,
        )
    return None


def _append_planner_message(
    state: CustomerAgentState,
    *,
    event_type: str,
    message: str,
    rationale: str,
) -> CustomerAgentState:
    next_state = state.model_copy(
        update={
            "messages": [
                *state.messages,
                ConversationMessage(role="assistant", content=message),
            ]
        }
    )
    next_state = append_response_quality_event(next_state, message, source="llm")
    return append_event(next_state, event_type, {"rationale": rationale})
