import pytest

from app.tools.mcp_retail_adapter import (
    McpGatewayResult,
    McpRetailAdapter,
    McpTransportError,
)
from app.tools.retail_port import RetailToolDefinition


class FakeGateway:
    def __init__(self, tools=None, error=None):
        self.tools = tools or []
        self.error = error

    def list_tools(self):
        if self.error:
            raise self.error
        return self.tools

    def call_tool(self, name, arguments):
        if self.error:
            raise self.error
        return McpGatewayResult(
            content={"order_id": arguments.get("order_id"), "status": "pending"},
            raw_content='{"order_id":"#W1","status":"pending"}',
            error=False,
        )

    def read_text_resource(self, uri):
        return {"retail://policy": "retail policy", "retail://db-hash": "hash-1"}[uri]


def _tool(name="get_order_details"):
    return RetailToolDefinition(
        name=name,
        tool_type="read",
        description="Get order",
        parameters_schema={"type": "object", "required": ["order_id"]},
    )


def test_mcp_adapter_maps_catalogue_metadata_and_results():
    adapter = McpRetailAdapter(FakeGateway([_tool()]))

    result = adapter.call_tool(
        "get_order_details", {"order_id": "#W1"}, call_id="call-1"
    )

    assert adapter.backend.managed_by_mcp is True
    assert adapter.backend.kind == "mcp_streamable_http"
    assert adapter.list_tools() == [_tool()]
    assert adapter.policy == "retail policy"
    assert adapter.db_hash() == "hash-1"
    assert result.call_id == "call-1"
    assert result.content["order_id"] == "#W1"


def test_mcp_adapter_does_not_fallback_when_transport_fails():
    adapter = McpRetailAdapter(FakeGateway(error=McpTransportError("offline")))

    with pytest.raises(McpTransportError, match="offline"):
        adapter.list_tools()


def test_mcp_adapter_rejects_missing_required_catalogue_tools():
    adapter = McpRetailAdapter(FakeGateway([_tool()]), required_tools={"get_user_details"})

    with pytest.raises(RuntimeError, match="missing required tools"):
        adapter.validate_catalogue()

