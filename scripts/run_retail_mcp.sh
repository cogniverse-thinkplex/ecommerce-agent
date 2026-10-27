#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHONPATH=backend:benchmarks/src benchmarks/.venv/bin/python -m uvicorn \
  app.mcp.retail_server:app \
  --host "${RETAIL_MCP_HOST:-127.0.0.1}" \
  --port "${RETAIL_MCP_PORT:-8765}"
