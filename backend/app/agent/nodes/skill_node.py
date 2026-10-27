from __future__ import annotations

from pydantic import BaseModel

from app.agent.nodes.tool_proposal_node import ToolProposal, ToolProposalResult
from app.agent.skills import SkillRegistry
from app.agent.state import CustomerAgentState, append_event


class SkillRouteResult(BaseModel):
    state: CustomerAgentState
    proposal: ToolProposal | None
    result: ToolProposalResult | None = None


def route_skill_action(
    state: CustomerAgentState,
    skill_registry: SkillRegistry | None,
    proposal: ToolProposal,
) -> SkillRouteResult:
    if not proposal.skill_id or not proposal.skill_action:
        return SkillRouteResult(state=state, proposal=proposal)
    if proposal.tool_name:
        return SkillRouteResult(state=state, proposal=proposal)
    if skill_registry is None:
        return SkillRouteResult(state=state, proposal=proposal)

    tool_name = skill_registry.resolve_tool(proposal.skill_id, proposal.skill_action)
    if tool_name is None:
        next_state = append_event(
            state,
            "skill_node.rejected",
            {
                "reason": "unknown_skill_action",
                "skill_id": proposal.skill_id,
                "skill_action": proposal.skill_action,
            },
        )
        return SkillRouteResult(
            state=next_state,
            proposal=proposal,
            result=ToolProposalResult(
                state=next_state,
                accepted=False,
                error=(
                    f"Skill action {proposal.skill_action} is not available "
                    f"for skill {proposal.skill_id}"
                ),
            ),
        )

    next_state = append_event(
        state,
        "skill_node.routed",
        {
            "skill_id": proposal.skill_id,
            "skill_action": proposal.skill_action,
            "tool": tool_name,
        },
    )
    return SkillRouteResult(
        state=next_state,
        proposal=proposal.model_copy(update={"tool_name": tool_name}),
    )
