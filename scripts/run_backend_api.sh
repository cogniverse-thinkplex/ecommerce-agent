#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

args=(
  app.api.main:app
  --host "${BACKEND_HOST:-127.0.0.1}"
  --port "${BACKEND_PORT:-8000}"
)

if [ "${BACKEND_RELOAD:-0}" = "1" ]; then
  args+=(--reload --reload-dir backend)
fi

PYTHONPATH=backend:benchmarks/src benchmarks/.venv/bin/python -m uvicorn "${args[@]}"
