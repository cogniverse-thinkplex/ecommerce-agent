from app.agent.proposal_generator import RuleBasedProposalGenerator
from app.agent.nodes.tool_node import ToolCallRequest
from app.agent.session_service import AgentSessionService
from app.tools.guarded_executor import GuardedRetailToolExecutor
from app.tools.tau_retail_adapter import TauRetailAdapter


def test_session_service_executes_real_tau_retail_read_tool():
    service = AgentSessionService(
        GuardedRetailToolExecutor(TauRetailAdapter.from_default_data())
    )
    service.start_session("conv-1")

    result = service.apply_tool_request(
        "conv-1",
        ToolCallRequest(
            name="find_user_id_by_name_zip",
            arguments={
                "first_name": "Yusuf",
                "last_name": "Rossi",
                "zip": "19122",
            },
            call_id="real-call-1",
        ),
    )

    assert result.executed is True
    assert result.state.messages[-2].role == "tool"
    assert result.state.messages[-2].content == "yusuf_rossi_9620"
    assert result.state.messages[-1].role == "assistant"
    assert result.state.messages[-1].content == "身份信息已确认。您可以继续查询订单或办理售后。"


def test_session_service_runtime_smoke_executes_real_tau_retail_lookup():
    service = AgentSessionService(
        GuardedRetailToolExecutor(TauRetailAdapter.from_default_data()),
        proposal_generator=RuleBasedProposalGenerator(),
    )
    service.start_session("conv-1")

    result = service.run_turn("conv-1", "Please find user Yusuf Rossi zip 19122")

    assert result.proposal is not None
    assert result.proposal.tool_name == "find_user_id_by_name_zip"
    assert result.proposal_result is not None
    assert result.proposal_result.accepted is True
    assert result.state.messages[-2].role == "tool"
    assert result.state.messages[-2].content == "yusuf_rossi_9620"
    assert result.state.messages[-1].role == "assistant"
    assert result.state.messages[-1].content == "身份信息已确认。您可以继续查询订单或办理售后。"


def test_session_service_blocks_real_tau_retail_write_tool_until_confirmation():
    service = AgentSessionService(
        GuardedRetailToolExecutor(TauRetailAdapter.from_default_data())
    )
    service.start_session("conv-1")

    result = service.apply_tool_request(
        "conv-1",
        ToolCallRequest(
            name="cancel_pending_order",
            arguments={"order_id": "#W0000000", "reason": "ordered by mistake"},
            call_id="real-call-2",
        ),
    )

    assert result.executed is False
    assert result.confirmation_required is True
    assert result.state.confirmation.pending is not None
    assert result.state.messages[-1].role == "assistant"
