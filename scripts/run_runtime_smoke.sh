#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHONPATH=backend:benchmarks/src benchmarks/.venv/bin/python -m app.evaluation.runtime_smoke "$@"
