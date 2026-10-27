from __future__ import annotations

from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from app.agent.nodes.tool_node import ToolCallRequest, ToolNodeResult, apply_tool_call
from app.agent.state import CustomerAgentState, append_event
from app.tools.guarded_executor import GuardedRetailToolExecutor


class ToolProposal(BaseModel):
    skill_id: str = ""
    skill_action: str = ""
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""
    call_id: str | None = None


class ToolProposalResult(BaseModel):
    state: CustomerAgentState
    accepted: bool
    tool_result: ToolNodeResult | None = None
    error: str | None = None


def apply_tool_proposal(
    state: CustomerAgentState,
    executor: GuardedRetailToolExecutor,
    proposal: ToolProposal,
) -> ToolProposalResult:
    if not proposal.tool_name:
        next_state = append_event(
            state,
            "tool_proposal.rejected",
            {"reason": "missing_tool_name", "rationale": proposal.rationale},
        )
        return ToolProposalResult(
            state=next_state,
            accepted=False,
            error="Tool proposal must include tool_name",
        )

    proposed_state = append_event(
        state,
        "tool_proposal.accepted",
        {
            "tool": proposal.tool_name,
            "rationale": proposal.rationale,
        },
    )
    tool_result = apply_tool_call(
        proposed_state,
        executor,
        ToolCallRequest(
            name=proposal.tool_name,
            arguments=proposal.arguments,
            call_id=proposal.call_id or f"proposal-{uuid4().hex}",
        ),
    )
    return ToolProposalResult(
        state=tool_result.state,
        accepted=True,
        tool_result=tool_result,
    )
