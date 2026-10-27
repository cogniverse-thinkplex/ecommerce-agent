from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
from typing import Any, Protocol
from uuid import uuid4

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from pydantic import AnyUrl

from app.tools.retail_port import (
    RetailToolDefinition,
    RetailToolResult,
    ToolBackendInfo,
)


class McpTransportError(RuntimeError):
    pass


@dataclass(frozen=True)
class McpGatewayResult:
    content: Any
    raw_content: str
    error: bool


class McpGateway(Protocol):
    def list_tools(self) -> list[RetailToolDefinition]: ...
    def call_tool(self, name: str, arguments: dict[str, Any]) -> McpGatewayResult: ...
    def read_text_resource(self, uri: str) -> str: ...


class HttpMcpGateway:
    def __init__(self, base_url: str, timeout_seconds: float = 30.0) -> None:
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds

    def list_tools(self) -> list[RetailToolDefinition]:
        async def operation(session: ClientSession):
            result = await session.list_tools()
            return [
                RetailToolDefinition(
                    name=tool.name,
                    tool_type=str((tool.meta or {}).get("tool_type", "read")),
                    description=tool.description or "",
                    parameters_schema=tool.inputSchema,
                )
                for tool in result.tools
            ]

        return self._run(operation)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> McpGatewayResult:
        async def operation(session: ClientSession):
            result = await session.call_tool(name, arguments)
            text = "".join(
                item.text for item in result.content if getattr(item, "type", None) == "text"
            )
            content = result.structuredContent
            if content is None:
                try:
                    content = json.loads(text)
                except json.JSONDecodeError:
                    content = text
            return McpGatewayResult(
                content=content,
                raw_content=text,
                error=bool(result.isError),
            )

        return self._run(operation)

    def read_text_resource(self, uri: str) -> str:
        async def operation(session: ClientSession):
            result = await session.read_resource(AnyUrl(uri))
            return "".join(
                item.text for item in result.contents if hasattr(item, "text")
            )

        return self._run(operation)

    def _run(self, operation):
        async def request():
            try:
                async with streamablehttp_client(
                    self.base_url, timeout=self.timeout_seconds
                ) as (read_stream, write_stream, _):
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        return await operation(session)
            except Exception as exc:
                raise McpTransportError(
                    f"MCP retail backend unavailable: {exc}"
                ) from exc

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(request())
        raise McpTransportError("Synchronous MCP adapter called from an async event loop")


class McpRetailAdapter:
    def __init__(
        self,
        gateway: McpGateway,
        required_tools: set[str] | None = None,
    ) -> None:
        self._gateway = gateway
        self._required_tools = required_tools or set()

    @classmethod
    def from_http(
        cls, base_url: str, timeout_seconds: float = 30.0
    ) -> "McpRetailAdapter":
        return cls(HttpMcpGateway(base_url, timeout_seconds))

    @property
    def backend(self) -> ToolBackendInfo:
        return ToolBackendInfo(
            kind="mcp_streamable_http",
            name="tau2-retail-mcp",
            managed_by_mcp=True,
        )

    @property
    def policy(self) -> str:
        return self._gateway.read_text_resource("retail://policy")

    def list_tools(self) -> list[RetailToolDefinition]:
        return sorted(self._gateway.list_tools(), key=lambda item: item.name)

    def validate_catalogue(self) -> None:
        available = {tool.name for tool in self.list_tools()}
        missing = sorted(self._required_tools - available)
        if missing:
            raise RuntimeError(f"MCP retail backend missing required tools: {missing}")

    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        call_id: str | None = None,
    ) -> RetailToolResult:
        result = self._gateway.call_tool(name, arguments)
        return RetailToolResult(
            call_id=call_id or f"mcp-{uuid4().hex}",
            name=name,
            content=result.content,
            raw_content=result.raw_content,
            error=result.error,
        )

    def db_hash(self) -> str | None:
        return self._gateway.read_text_resource("retail://db-hash") or None

