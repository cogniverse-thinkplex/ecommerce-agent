import asyncio

from app.mcp.retail_server import build_retail_mcp_server
from app.tools.tau_retail_adapter import TauRetailAdapter


def test_retail_mcp_server_exposes_same_tool_catalogue_as_tau_adapter():
    adapter = TauRetailAdapter.from_default_data()
    server = build_retail_mcp_server(adapter)

    result = asyncio.run(server._list_tools())

    expected = {tool.name: tool.parameters_schema for tool in adapter.list_tools()}
    assert {tool.name: tool.inputSchema for tool in result} == expected
    assert len(result) == 16

