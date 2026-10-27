from __future__ import annotations

from contextlib import asynccontextmanager
import os
from typing import Any

from mcp import types
from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.routing import Route

from app.tools.retail_port import RetailToolPort
from app.tools.tau_retail_adapter import TauRetailAdapter


class RetailMcpServer:
    def __init__(self, adapter: RetailToolPort) -> None:
        self.adapter = adapter
        self.server = Server("tau2-retail-mcp", version="1.0.0")
        self._register_handlers()

    async def _list_tools(self) -> list[types.Tool]:
        return [
            types.Tool(
                name=tool.name,
                description=tool.description,
                inputSchema=tool.parameters_schema,
                _meta={"tool_type": tool.tool_type},
            )
            for tool in self.adapter.list_tools()
        ]

    def _register_handlers(self) -> None:
        self.server.list_tools()(self._list_tools)

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any]):
            result = self.adapter.call_tool(name, arguments)
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=result.raw_content)],
                structuredContent=(result.content if isinstance(result.content, dict) else None),
                isError=result.error,
            )

        @self.server.list_resources()
        async def list_resources():
            return [
                types.Resource(
                    name="retail-policy",
                    uri="retail://policy",
                    mimeType="text/plain",
                ),
                types.Resource(
                    name="retail-db-hash",
                    uri="retail://db-hash",
                    mimeType="text/plain",
                ),
            ]

        @self.server.read_resource()
        async def read_resource(uri):
            value = str(uri)
            if value == "retail://policy":
                return self.adapter.policy
            if value == "retail://db-hash":
                db_hash = getattr(self.adapter, "db_hash", lambda: None)()
                return db_hash or ""
            raise ValueError(f"Unknown retail resource: {value}")

    def asgi_app(self) -> Starlette:
        manager = StreamableHTTPSessionManager(
            app=self.server,
            json_response=True,
            stateless=True,
        )

        class Endpoint:
            async def __call__(self, scope, receive, send):
                await manager.handle_request(scope, receive, send)

        @asynccontextmanager
        async def lifespan(_app):
            async with manager.run():
                yield

        return Starlette(
            routes=[Route("/mcp", endpoint=Endpoint())],
            lifespan=lifespan,
        )


def build_retail_mcp_server(
    adapter: RetailToolPort | None = None,
) -> RetailMcpServer:
    return RetailMcpServer(adapter or TauRetailAdapter.from_default_data())


def create_mcp_app() -> Starlette:
    return build_retail_mcp_server().asgi_app()


app = create_mcp_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("RETAIL_MCP_HOST", "127.0.0.1"),
        port=int(os.getenv("RETAIL_MCP_PORT", "8765")),
    )

