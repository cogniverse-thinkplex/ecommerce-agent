import asyncio

from app.agent.proposal_generator import LLMProposalGenerator, RuleBasedProposalGenerator
from app.agent.runtime import BaselineAgentRuntime, LLMPlannerRuntime
from app.agent.session_service import AgentSessionService
from app.api.main import build_agent_runtime, build_proposal_generator
from app.api.main import create_app
from app.tools.guarded_executor import GuardedRetailToolExecutor
from app.tools.retail_port import RetailToolDefinition, RetailToolResult, ToolBackendInfo
from fastapi.testclient import TestClient


def test_build_proposal_generator_defaults_to_llm(monkeypatch):
    monkeypatch.delenv("ECOM_AGENT_PROPOSAL_GENERATOR", raising=False)
    monkeypatch.delenv("ECOM_AGENT_PROPOSAL_LLM", raising=False)

    generator = build_proposal_generator()

    assert isinstance(generator, LLMProposalGenerator)
    assert generator.model == "dashscope/qwen3.8-max"


def test_app_config_api_reports_planner_type(monkeypatch):
    monkeypatch.delenv("ECOM_AGENT_PROPOSAL_GENERATOR", raising=False)

    response = TestClient(create_app()).get("/config")

    assert response.status_code == 200
    assert response.json()["planner_type"] == "llm"


def test_app_config_api_reports_backend_and_policy(monkeypatch):
    monkeypatch.delenv("ECOM_AGENT_PROPOSAL_GENERATOR", raising=False)
    service = AgentSessionService(
        GuardedRetailToolExecutor(EmptyPort()),
        proposal_generator=RuleBasedProposalGenerator(),
    )

    response = TestClient(create_app(service=service)).get("/config")

    assert response.status_code == 200
    assert response.json() == {
        "planner_type": "rule",
        "proposal_model": None,
        "tool_backend": {
            "kind": "empty",
            "name": "empty-retail",
            "managed_by_mcp": False,
        },
        "policy_summary": "Empty policy.",
    }


def test_build_proposal_generator_uses_llm_when_configured(monkeypatch):
    monkeypatch.setenv("ECOM_AGENT_PROPOSAL_GENERATOR", "llm")
    monkeypatch.setenv("ECOM_AGENT_PROPOSAL_LLM", "dashscope/deepseek-v4-pro-0813")

    generator = build_proposal_generator()

    assert isinstance(generator, LLMProposalGenerator)
    assert generator.model == "dashscope/deepseek-v4-pro-0813"


def test_build_agent_runtime_wraps_configured_proposal_generator(monkeypatch):
    monkeypatch.setenv("ECOM_AGENT_PROPOSAL_GENERATOR", "llm")
    monkeypatch.setenv("ECOM_AGENT_PROPOSAL_LLM", "dashscope/deepseek-v4-pro-0813")

    runtime = build_agent_runtime(GuardedRetailToolExecutor(EmptyPort()))

    assert isinstance(runtime, LLMPlannerRuntime)
    assert isinstance(runtime.proposal_generator, LLMProposalGenerator)
    assert runtime.proposal_generator.model == "dashscope/deepseek-v4-pro-0813"
    tools, policy = runtime.proposal_generator.loaded_context
    assert policy == "Empty policy."
    assert tools == [
        RetailToolDefinition(
            name="get_order_details",
            tool_type="read",
            description="Fetch order details.",
            parameters_schema={"required": ["order_id"]},
        )
    ]
    assert runtime.proposal_generator.skill_registry is not None
    assert [
        skill.id for skill in runtime.proposal_generator.skill_registry
    ][:3] == ["authentication", "order_lookup", "cancel_order"]


def test_llm_generator_defers_mcp_context_until_outside_running_event_loop(monkeypatch):
    monkeypatch.setenv("ECOM_AGENT_PROPOSAL_GENERATOR", "llm")
    executor = GuardedRetailToolExecutor(LoopRejectingPort())

    async def build_inside_server_loop():
        return build_proposal_generator(executor=executor)

    generator = asyncio.run(build_inside_server_loop())

    assert isinstance(generator, LLMProposalGenerator)
    tools, policy = generator.loaded_context
    assert policy == "Loop-safe policy."
    assert tools[0].name == "get_order_details"


class EmptyPort:
    @property
    def backend(self) -> ToolBackendInfo:
        return ToolBackendInfo(
            kind="empty",
            name="empty-retail",
            managed_by_mcp=False,
        )

    @property
    def policy(self) -> str:
        return "Empty policy."

    def list_tools(self) -> list[RetailToolDefinition]:
        return [
            RetailToolDefinition(
                name="get_order_details",
                tool_type="read",
                description="Fetch order details.",
                parameters_schema={"required": ["order_id"]},
            )
        ]

    def call_tool(
        self,
        name: str,
        arguments: dict,
        call_id: str | None = None,
    ) -> RetailToolResult:
        raise AssertionError("No tool should be called while building runtime")


class LoopRejectingPort(EmptyPort):
    @property
    def policy(self) -> str:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return "Loop-safe policy."
        raise RuntimeError("called inside event loop")

    def list_tools(self) -> list[RetailToolDefinition]:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return super().list_tools()
        raise RuntimeError("called inside event loop")
