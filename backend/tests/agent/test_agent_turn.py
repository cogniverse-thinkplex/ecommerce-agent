from typing import Any

from app.agent.proposal_generator import RuleBasedProposalGenerator
from app.agent.session_service import AgentSessionService
from app.tools.guarded_executor import GuardedRetailToolExecutor
from app.tools.retail_port import RetailToolDefinition, RetailToolResult


def test_session_service_run_turn_adds_user_message_and_executes_generated_proposal():
    service = AgentSessionService(
        GuardedRetailToolExecutor(
            RecordingPort(
                [
                    RetailToolDefinition(
                        name="find_user_id_by_name_zip",
                        tool_type="read",
                        description="",
                        parameters_schema={},
                    )
                ]
            )
        ),
        proposal_generator=RuleBasedProposalGenerator(),
    )
    service.start_session("conv-1")

    result = service.run_turn("conv-1", "Please find user Yusuf Rossi zip 19122")

    assert result.proposal is not None
    assert result.proposal.tool_name == "find_user_id_by_name_zip"
    assert result.proposal_result is not None
    assert result.proposal_result.accepted is True
    assert result.state.messages[0].role == "user"
    assert result.state.messages[-2].role == "tool"
    assert result.state.messages[-1].role == "assistant"
    assert result.state.messages[-1].content == "身份信息已确认。您可以继续查询订单或办理售后。"


def test_session_service_run_turn_summarizes_product_option_count():
    service = AgentSessionService(
        GuardedRetailToolExecutor(
            RecordingPort(
                [
                    RetailToolDefinition(
                        name="get_product_details",
                        tool_type="read",
                        description="",
                        parameters_schema={},
                    )
                ],
                responses={
                    "get_product_details": {
                        "content": {
                            "name": "T-Shirt",
                            "product_id": "9523456873",
                            "variants": {
                                "available-small": {"available": True},
                                "available-large": {"available": True},
                                "sold-out": {"available": False},
                            },
                        },
                        "raw_content": (
                            '{"name":"T-Shirt","product_id":"9523456873",'
                            '"variants":{"available-small":{"available":true},'
                            '"available-large":{"available":true},'
                            '"sold-out":{"available":false}}}'
                        ),
                    }
                },
            )
        ),
        proposal_generator=RuleBasedProposalGenerator(),
    )
    service.start_session("conv-1")

    result = service.run_turn("conv-1", "How many tshirt options are available?")

    assert result.proposal is not None
    assert result.proposal.tool_name == "get_product_details"
    assert result.state.messages[-1].role == "assistant"
    assert "T-Shirt 当前有 2 个可选规格" in result.state.messages[-1].content
    quality_event = next(
        event for event in result.state.events if event.event_type == "response.quality_checked"
    )
    assert quality_event.payload["source"] == "tool"
    assert quality_event.payload["passed"] is True


def test_session_service_run_turn_records_assistant_message_when_no_proposal():
    service = AgentSessionService(
        GuardedRetailToolExecutor(RecordingPort([])),
        proposal_generator=RuleBasedProposalGenerator(),
    )
    service.start_session("conv-1")

    result = service.run_turn("conv-1", "hello there")

    assert result.proposal is None
    assert result.proposal_result is None
    assert result.state.messages[-1].role == "assistant"
    assert "请补充" in result.state.messages[-1].content


class RecordingPort:
    def __init__(
        self,
        tools: list[RetailToolDefinition],
        responses: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._tools = tools
        self._responses = responses or {}

    @property
    def policy(self) -> str:
        return ""

    def list_tools(self) -> list[RetailToolDefinition]:
        return self._tools

    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        call_id: str | None = None,
    ) -> RetailToolResult:
        response = self._responses.get(name)
        if response is not None:
            return RetailToolResult(
                call_id=call_id or "generated-call-id",
                name=name,
                content=response["content"],
                raw_content=response["raw_content"],
                error=False,
            )
        return RetailToolResult(
            call_id=call_id or "generated-call-id",
            name=name,
            content={"user_id": "yusuf_rossi_9620"},
            raw_content='{"user_id": "yusuf_rossi_9620"}',
            error=False,
        )
