from __future__ import annotations

from app.agent.nodes.tool_proposal_node import ToolProposal, ToolProposalResult
from app.agent.skills import SkillRegistry
from app.agent.state import CustomerAgentState, append_event
from app.tools.retail_port import RetailToolDefinition


def validate_tool_proposal(
    state: CustomerAgentState,
    tools: list[RetailToolDefinition],
    proposal: ToolProposal,
) -> ToolProposalResult | None:
    tool = _find_tool_definition(tools, proposal.tool_name)
    if tool is None:
        next_state = append_event(
            state,
            "tool_proposal.rejected",
            {"reason": "unknown_tool", "tool": proposal.tool_name},
        )
        return ToolProposalResult(
            state=next_state,
            accepted=False,
            error=f"Unknown tool proposal: {proposal.tool_name}",
        )

    missing_arguments = _missing_required_arguments(
        tool.parameters_schema,
        proposal.arguments,
    )
    if missing_arguments:
        next_state = append_event(
            state,
            "tool_proposal.rejected",
            {
                "reason": "missing_required_arguments",
                "tool": proposal.tool_name,
                "missing": missing_arguments,
            },
        )
        return ToolProposalResult(
            state=next_state,
            accepted=False,
            error="Missing required tool arguments: " + ", ".join(missing_arguments),
        )

    return None


def validate_skill_policy(
    state: CustomerAgentState,
    skill_registry: SkillRegistry | None,
    proposal: ToolProposal,
) -> ToolProposalResult | None:
    if not proposal.skill_id or skill_registry is None:
        return None

    skill = skill_registry.find(proposal.skill_id)
    if skill is None:
        next_state = append_event(
            state,
            "skill_policy.rejected",
            {
                "reason": "unknown_skill",
                "skill_id": proposal.skill_id,
                "tool": proposal.tool_name,
            },
        )
        return ToolProposalResult(
            state=next_state,
            accepted=False,
            error=f"Unknown skill: {proposal.skill_id}",
        )

    if proposal.tool_name not in skill.allowed_tools:
        next_state = append_event(
            state,
            "skill_policy.rejected",
            {
                "reason": "tool_not_allowed",
                "skill_id": proposal.skill_id,
                "tool": proposal.tool_name,
            },
        )
        return ToolProposalResult(
            state=next_state,
            accepted=False,
            error=(
                f"Tool {proposal.tool_name} is not allowed "
                f"for skill {proposal.skill_id}"
            ),
        )

    return None


def _find_tool_definition(
    tools: list[RetailToolDefinition],
    name: str,
) -> RetailToolDefinition | None:
    for tool in tools:
        if tool.name == name:
            return tool
    return None


def _missing_required_arguments(
    parameters_schema: dict,
    arguments: dict,
) -> list[str]:
    required = parameters_schema.get("required")
    if not isinstance(required, list):
        return []
    return [
        name
        for name in required
        if isinstance(name, str) and name not in arguments
    ]
