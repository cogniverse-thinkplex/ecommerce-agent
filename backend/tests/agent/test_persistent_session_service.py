from __future__ import annotations

from pathlib import Path

from app.agent.nodes.tool_node import ToolCallRequest
from app.agent.session_service import AgentSessionService
from app.agent.session_store import PersistentSessionStore
from app.persistence.sqlite import SqliteUnitOfWork
from app.tools.guarded_executor import GuardedRetailToolExecutor
from app.tools.retail_port import RetailToolDefinition, RetailToolResult, ToolBackendInfo


class WritePort:
    @property
    def backend(self) -> ToolBackendInfo:
        return ToolBackendInfo(kind="test", name="test", managed_by_mcp=False)

    @property
    def policy(self) -> str:
        return "test policy"

    def list_tools(self) -> list[RetailToolDefinition]:
        return [
            RetailToolDefinition(
                name="cancel_pending_order",
                tool_type="write",
                description="cancel",
                parameters_schema={"type": "object"},
            )
        ]

    def call_tool(self, name, arguments, call_id=None) -> RetailToolResult:
        return RetailToolResult(
            call_id=call_id or "call-1",
            name=name,
            content={"status": "cancelled"},
            raw_content='{"status":"cancelled"}',
            error=False,
        )

    def db_hash(self) -> str:
        return "hash"


def _service(path: Path) -> AgentSessionService:
    unit = SqliteUnitOfWork(path)
    unit.initialize()
    return AgentSessionService(
        GuardedRetailToolExecutor(WritePort()),
        session_store=PersistentSessionStore(unit),
    )


def test_persistent_service_reloads_messages_after_reconstruction(tmp_path: Path):
    path = tmp_path / "agent.db"
    first = _service(path)
    first.start_session("conv-1")
    first.add_user_message("conv-1", "hello")

    second = _service(path)

    assert second.get_session("conv-1").messages[-1].content == "hello"
    assert second.list_sessions()[0].message_count == 1


def test_pending_confirmation_survives_service_reconstruction(tmp_path: Path):
    path = tmp_path / "agent.db"
    first = _service(path)
    first.start_session("conv-1")
    first.apply_tool_request(
        "conv-1",
        ToolCallRequest(
            name="cancel_pending_order",
            arguments={"order_id": "#W2378156", "reason": "ordered by mistake"},
        ),
    )

    second = _service(path)
    pending = second.get_session("conv-1").confirmation.pending

    assert pending is not None
    assert pending.name == "cancel_pending_order"


def test_deleting_persistent_session_archives_it(tmp_path: Path):
    path = tmp_path / "agent.db"
    first = _service(path)
    first.start_session("conv-1")
    first.delete_session("conv-1")

    second = _service(path)

    assert second.list_sessions() == []

