from app.agent.nodes.proposal_validation_node import (
    validate_skill_policy,
    validate_tool_proposal,
)
from app.agent.nodes.tool_proposal_node import ToolProposal
from app.agent.skills import default_skill_registry
from app.agent.state import CustomerAgentState
from app.tools.retail_port import RetailToolDefinition


def _user_lookup_tool() -> RetailToolDefinition:
    return RetailToolDefinition(
        name="find_user_id_by_name_zip",
        tool_type="read",
        description="Find user by name and zip.",
        parameters_schema={
            "type": "object",
            "required": ["name", "zip"],
            "properties": {
                "name": {"type": "string"},
                "zip": {"type": "string"},
            },
        },
    )


def test_validate_tool_proposal_rejects_unknown_tool():
    state = CustomerAgentState(conversation_id="conv-1")
    proposal = ToolProposal(tool_name="missing_tool", arguments={})

    rejected = validate_tool_proposal(state, [_user_lookup_tool()], proposal)

    assert rejected is not None
    assert rejected.accepted is False
    assert rejected.error == "Unknown tool proposal: missing_tool"
    assert rejected.state.events[-1].event_type == "tool_proposal.rejected"
    assert rejected.state.events[-1].payload == {
        "reason": "unknown_tool",
        "tool": "missing_tool",
    }


def test_validate_tool_proposal_rejects_missing_required_arguments():
    state = CustomerAgentState(conversation_id="conv-1")
    proposal = ToolProposal(
        tool_name="find_user_id_by_name_zip",
        arguments={"name": "Yusuf Rossi"},
    )

    rejected = validate_tool_proposal(state, [_user_lookup_tool()], proposal)

    assert rejected is not None
    assert rejected.accepted is False
    assert rejected.error == "Missing required tool arguments: zip"
    assert rejected.state.events[-1].event_type == "tool_proposal.rejected"
    assert rejected.state.events[-1].payload == {
        "reason": "missing_required_arguments",
        "tool": "find_user_id_by_name_zip",
        "missing": ["zip"],
    }


def test_validate_skill_policy_rejects_tool_outside_skill_boundary():
    state = CustomerAgentState(conversation_id="conv-1")
    proposal = ToolProposal(
        skill_id="authentication",
        tool_name="get_order_details",
        arguments={"order_id": "#W2378156"},
    )

    rejected = validate_skill_policy(state, default_skill_registry(), proposal)

    assert rejected is not None
    assert rejected.accepted is False
    assert rejected.error == (
        "Tool get_order_details is not allowed for skill authentication"
    )
    assert rejected.state.events[-1].event_type == "skill_policy.rejected"
    assert rejected.state.events[-1].payload == {
        "reason": "tool_not_allowed",
        "skill_id": "authentication",
        "tool": "get_order_details",
    }
