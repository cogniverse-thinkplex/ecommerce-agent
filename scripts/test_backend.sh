#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

has_test_target=false
for arg in "$@"; do
  if [[ "$arg" != -* ]]; then
    has_test_target=true
    break
  fi
done

if [ "$has_test_target" = false ]; then
  set -- backend/tests "$@"
fi

PYTHONPATH=backend:benchmarks/src benchmarks/.venv/bin/python -m pytest "$@"
