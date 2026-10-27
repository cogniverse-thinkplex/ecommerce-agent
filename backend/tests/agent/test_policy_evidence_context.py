from app.agent.proposal_generator import _build_llm_planner_user_context
from app.agent.state import AgentEvent, CustomerAgentState


def test_planner_context_contains_latest_policy_evidence():
    state=CustomerAgentState(conversation_id="c", events=[AgentEvent(event_type="rag.completed", payload={"hits":[{"policy_id":"returns","title":"退货政策","content":"七日内可申请","scope":"符合条件商品","source_url":"https://example.com","verified_at":"2026-10-24"}]})])
    context=_build_llm_planner_user_context(state,"能退吗",tool_catalog=[],skill_registry=[],policy="")
    assert "POLICY_EVIDENCE:" in context
    assert "七日内可申请" in context
