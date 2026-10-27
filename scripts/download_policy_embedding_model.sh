#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CACHE="${ECOM_POLICY_MODEL_CACHE:-$ROOT/data/models}"
MODEL="${ECOM_POLICY_EMBEDDING_MODEL:-BAAI/bge-small-zh-v1.5}"

mkdir -p "$CACHE"
ECOM_POLICY_MODEL_LOCAL_ONLY=false ECOM_POLICY_MODEL_CACHE="$CACHE" ECOM_POLICY_EMBEDDING_MODEL="$MODEL" \
  "$ROOT/benchmarks/.venv/bin/python" -c \
  'from sentence_transformers import SentenceTransformer; import os; SentenceTransformer(os.environ["ECOM_POLICY_EMBEDDING_MODEL"], cache_folder=os.environ["ECOM_POLICY_MODEL_CACHE"])'
echo "Policy embedding model cached: $MODEL -> $CACHE"
