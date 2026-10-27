from __future__ import annotations

import os

from app.tools.retail_port import RetailToolPort
from app.tools.tau_retail_adapter import TauRetailAdapter
from app.tools.mcp_retail_adapter import McpRetailAdapter


def build_retail_tool_port() -> RetailToolPort:
    backend = os.getenv("ECOM_AGENT_TOOL_BACKEND", "tau2_python").strip().lower()
    if backend == "tau2_python":
        return TauRetailAdapter.from_default_data()
    if backend == "mcp":
        return McpRetailAdapter.from_http(
            os.getenv("ECOM_AGENT_MCP_URL", "http://127.0.0.1:8765/mcp"),
            float(os.getenv("ECOM_AGENT_MCP_TIMEOUT_SECONDS", "30")),
        )
    raise ValueError(f"Unsupported retail tool backend: {backend}")
