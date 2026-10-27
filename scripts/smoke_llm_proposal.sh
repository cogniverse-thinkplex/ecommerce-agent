#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [ "${RUN_LLM_SMOKE:-0}" != "1" ]; then
  echo "Set RUN_LLM_SMOKE=1 to call the configured proposal LLM."
  exit 0
fi

PYTHONPATH=backend:benchmarks/src benchmarks/.venv/bin/python - <<'PY'
from app.agent.proposal_generator import LLMProposalGenerator, LiteLLMClient
from app.agent.state import CustomerAgentState
import os

model = os.getenv("ECOM_AGENT_PROPOSAL_LLM", "dashscope/deepseek-v4-pro-0813")
generator = LLMProposalGenerator(model=model, client=LiteLLMClient())
proposal = generator.generate(
    CustomerAgentState(conversation_id="smoke-1"),
    "Please find user Yusuf Rossi zip 19122",
)
print(proposal.model_dump_json(indent=2) if proposal else "NO_PROPOSAL")
PY
