#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BENCHMARKS_DIR="$ROOT_DIR/benchmarks"

if [[ ! -d "$BENCHMARKS_DIR" ]]; then
  echo "Missing benchmarks directory: $BENCHMARKS_DIR" >&2
  exit 1
fi

if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
fi

AGENT_LLM="${TAU2_AGENT_LLM:-openai/gpt-4.1-mini}"
USER_LLM="${TAU2_USER_LLM:-openai/gpt-4.1-mini}"
NUM_TASKS="${TAU2_NUM_TASKS:-5}"
NUM_TRIALS="${TAU2_NUM_TRIALS:-1}"
MAX_CONCURRENCY="${TAU2_MAX_CONCURRENCY:-1}"
SAVE_TO="${TAU2_SAVE_TO:-p0_retail_baseline}"

cd "$BENCHMARKS_DIR"

/opt/miniconda3/envs/ecom-agent/bin/uv run tau2 run \
  --domain retail \
  --agent llm_agent \
  --agent-llm "$AGENT_LLM" \
  --user-llm "$USER_LLM" \
  --num-trials "$NUM_TRIALS" \
  --num-tasks "$NUM_TASKS" \
  --max-concurrency "$MAX_CONCURRENCY" \
  --save-to "$SAVE_TO" \
  --auto-resume \
  --log-level INFO
