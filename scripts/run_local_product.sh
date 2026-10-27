#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export ECOM_AGENT_STORE="${ECOM_AGENT_STORE:-sqlite}"
export ECOM_AGENT_SQLITE_PATH="${ECOM_AGENT_SQLITE_PATH:-data/ecommerce_agent.db}"
export ECOM_AGENT_TOOL_BACKEND="${ECOM_AGENT_TOOL_BACKEND:-mcp}"
export ECOM_AGENT_MCP_URL="${ECOM_AGENT_MCP_URL:-http://127.0.0.1:8765/mcp}"
export ECOM_AGENT_PROPOSAL_GENERATOR="${ECOM_AGENT_PROPOSAL_GENERATOR:-llm}"
export ECOM_AGENT_PROPOSAL_LLM="${ECOM_AGENT_PROPOSAL_LLM:-dashscope/qwen3.8-max}"

mkdir -p "$(dirname "$ECOM_AGENT_SQLITE_PATH")"

scripts/run_retail_mcp.sh &
MCP_PID=$!
API_PID=""

cleanup() {
  if [[ -n "$API_PID" ]]; then kill "$API_PID" 2>/dev/null || true; fi
  kill "$MCP_PID" 2>/dev/null || true
  wait "$MCP_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

mcp_ready=false
for _ in {1..60}; do
  if curl -fsS -o /dev/null -X POST \
    -H 'content-type: application/json' \
    -H 'accept: application/json, text/event-stream' \
    --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"startup","version":"1"}}}' \
    "$ECOM_AGENT_MCP_URL"; then
    mcp_ready=true
    break
  fi
  sleep 0.25
done

if [[ "$mcp_ready" != "true" ]]; then
  echo "MCP 服务未能在规定时间内启动。" >&2
  exit 1
fi

scripts/run_backend_api.sh &
API_PID=$!
echo "客服中心: http://127.0.0.1:${BACKEND_PORT:-8000}/support/"
echo "工程控制台: http://127.0.0.1:${BACKEND_PORT:-8000}/dashboard/"
wait "$API_PID"
