from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from tau2.data_model.message import ToolCall
from tau2.domains.retail.environment import get_environment
from tau2.environment.environment import Environment

from app.tools.retail_port import (
    RetailToolDefinition,
    RetailToolResult,
    ToolBackendInfo,
)


class TauRetailAdapter:
    def __init__(self, environment: Environment) -> None:
        self._environment = environment

    @classmethod
    def from_default_data(cls) -> "TauRetailAdapter":
        return cls(get_environment())

    @property
    def backend(self) -> ToolBackendInfo:
        return ToolBackendInfo(
            kind="tau2_python",
            name="tau2-retail",
            managed_by_mcp=False,
        )

    @property
    def policy(self) -> str:
        return self._environment.get_policy()

    def list_tools(self) -> list[RetailToolDefinition]:
        tools = []
        toolkit = self._environment.tools
        if toolkit is None:
            return tools
        for tool in self._environment.get_tools():
            tools.append(
                RetailToolDefinition(
                    name=tool.name,
                    tool_type=toolkit.tool_type(tool.name).value,
                    description=tool.short_desc,
                    parameters_schema=tool.openai_schema["function"]["parameters"],
                )
            )
        return sorted(tools, key=lambda item: item.name)

    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        call_id: str | None = None,
    ) -> RetailToolResult:
        resolved_call_id = call_id or f"tool-{uuid4().hex}"
        response = self._environment.get_response(
            ToolCall(
                id=resolved_call_id,
                name=name,
                arguments=arguments,
                requestor="assistant",
            )
        )
        return RetailToolResult(
            call_id=response.id,
            name=name,
            content=_parse_tool_content(response.content),
            raw_content=response.content,
            error=response.error,
        )

    def db_hash(self) -> str | None:
        return self._environment.get_db_hash()


def _parse_tool_content(content: str) -> Any:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return content
