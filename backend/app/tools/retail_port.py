from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class RetailToolDefinition:
    name: str
    tool_type: str
    description: str
    parameters_schema: dict[str, Any]


@dataclass(frozen=True)
class RetailToolResult:
    call_id: str
    name: str
    content: Any
    raw_content: str
    error: bool


@dataclass(frozen=True)
class ToolBackendInfo:
    kind: str
    name: str
    managed_by_mcp: bool


class RetailToolPort(Protocol):
    @property
    def backend(self) -> ToolBackendInfo:
        raise NotImplementedError

    @property
    def policy(self) -> str:
        raise NotImplementedError

    def list_tools(self) -> list[RetailToolDefinition]:
        raise NotImplementedError

    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        call_id: str | None = None,
    ) -> RetailToolResult:
        raise NotImplementedError
