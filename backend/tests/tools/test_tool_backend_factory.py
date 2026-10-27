import pytest

from app.tools.tau_retail_adapter import TauRetailAdapter
from app.tools.tool_backend_factory import build_retail_tool_port


def test_build_retail_tool_port_defaults_to_tau2_python(monkeypatch):
    monkeypatch.delenv("ECOM_AGENT_TOOL_BACKEND", raising=False)

    port = build_retail_tool_port()

    assert isinstance(port, TauRetailAdapter)
    assert port.backend.kind == "tau2_python"
    assert port.backend.managed_by_mcp is False


def test_build_retail_tool_port_builds_mcp_adapter(monkeypatch):
    monkeypatch.setenv("ECOM_AGENT_TOOL_BACKEND", "mcp")
    monkeypatch.setenv("ECOM_AGENT_MCP_URL", "http://127.0.0.1:8765/mcp")

    port = build_retail_tool_port()

    assert port.backend.managed_by_mcp is True
    assert port.backend.kind == "mcp_streamable_http"


def test_build_retail_tool_port_rejects_unknown_backend(monkeypatch):
    monkeypatch.setenv("ECOM_AGENT_TOOL_BACKEND", "banana")

    with pytest.raises(ValueError, match="Unsupported retail tool backend"):
        build_retail_tool_port()
