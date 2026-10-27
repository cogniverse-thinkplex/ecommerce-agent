from app.agent.nodes.skill_node import route_skill_action
from app.agent.nodes.tool_proposal_node import ToolProposal
from app.agent.skills import default_skill_registry
from app.agent.state import CustomerAgentState


def test_route_skill_action_fills_tool_from_skill_action():
    state = CustomerAgentState(conversation_id="conv-1")
    proposal = ToolProposal(
        skill_id="authentication",
        skill_action="lookup_by_name_zip",
        tool_name="",
        arguments={"name": "Yusuf Rossi", "zip": "19122"},
    )

    routed = route_skill_action(state, default_skill_registry(), proposal)

    assert routed.result is None
    assert routed.proposal is not None
    assert routed.proposal.tool_name == "find_user_id_by_name_zip"
    assert routed.state.events[-1].event_type == "skill_node.routed"
    assert routed.state.events[-1].payload == {
        "skill_id": "authentication",
        "skill_action": "lookup_by_name_zip",
        "tool": "find_user_id_by_name_zip",
    }


def test_route_skill_action_rejects_unknown_skill_action():
    state = CustomerAgentState(conversation_id="conv-1")
    proposal = ToolProposal(
        skill_id="order_lookup",
        skill_action="lookup_by_name_zip",
        tool_name="",
        arguments={},
    )

    routed = route_skill_action(state, default_skill_registry(), proposal)

    assert routed.result is not None
    assert routed.result.accepted is False
    assert routed.result.error == (
        "Skill action lookup_by_name_zip is not available for skill order_lookup"
    )
    assert routed.state.events[-1].event_type == "skill_node.rejected"
    assert routed.state.events[-1].payload["reason"] == "unknown_skill_action"
