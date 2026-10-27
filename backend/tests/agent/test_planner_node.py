from app.agent.nodes.planner_node import apply_planner_decision
from app.agent.proposal_generator import PlannerDecision
from app.agent.state import CustomerAgentState


def test_apply_planner_decision_appends_final_response_message():
    state = CustomerAgentState(conversation_id="conv-1")

    next_state = apply_planner_decision(
        state,
        PlannerDecision(
            action="final_response",
            message="订单已经处理好了。",
            rationale="order complete",
        ),
    )

    assert next_state is not None
    assert next_state.messages[-1].role == "assistant"
    assert next_state.messages[-1].content == "订单已经处理好了。"
    assert next_state.events[-1].event_type == "planner.final_response"
    assert next_state.events[-1].payload == {"rationale": "order complete"}
    quality_event = next(event for event in next_state.events if event.event_type == "response.quality_checked")
    assert quality_event.payload == {
        "source": "llm",
        "passed": False,
        "issue_codes": ["missing_next_step"],
        "policy_evidence_available": False,
        "policy_evidence_count": 0,
    }


def test_apply_planner_decision_records_invalid_planner_output():
    state = CustomerAgentState(conversation_id="conv-1")

    next_state = apply_planner_decision(
        state,
        PlannerDecision(action="invalid", error="bad json"),
    )

    assert next_state is not None
    assert next_state.events[-1].event_type == "planner.invalid_output"
    assert next_state.events[-1].payload == {"error": "bad json"}
