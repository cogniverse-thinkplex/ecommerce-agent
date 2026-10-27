#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

./scripts/test_backend.sh -q
node scripts/validate_observability_ui.mjs

# Browser rendering is validated separately against a running product stack with
# scripts/validate_support_ui.mjs; its API and static contracts are covered above.

./scripts/check_runtime_regression.sh \
  benchmarks/data/simulations/regression-rule-e9-write-workflows/runtime_subset.json \
  --required-confirmed-outcomes 5 \
  --required-total-tasks 5 \
  --expected-planner-type rule

./scripts/check_runtime_regression.sh \
  benchmarks/data/simulations/regression-llm-e10-qwen37-flash-usage/runtime_subset.json \
  --required-confirmed-outcomes 5 \
  --required-total-tasks 5 \
  --expected-planner-type llm \
  --max-average-estimated-cost-cny 0.02

E11_ARTIFACT="benchmarks/data/simulations/regression-rule-e11-expanded/runtime_subset.json"
if [[ -f "$E11_ARTIFACT" ]]; then
  ./scripts/check_runtime_regression.sh "$E11_ARTIFACT" \
    --required-confirmed-outcomes 5 \
    --required-total-tasks 9 \
    --expected-planner-type rule
fi

E11_LLM_ARTIFACT="benchmarks/data/simulations/regression-llm-e11-expanded-qwen37-flash-20260715/runtime_subset.json"
if [[ -f "$E11_LLM_ARTIFACT" ]]; then
  ./scripts/check_runtime_regression.sh "$E11_LLM_ARTIFACT" \
    --required-confirmed-outcomes 5 \
    --required-total-tasks 9 \
    --expected-planner-type llm \
    --max-average-estimated-cost-cny 0.02
fi

E12_RULE_ARTIFACT="benchmarks/data/simulations/regression-rule-e12-routing/runtime_subset.json"
if [[ -f "$E12_RULE_ARTIFACT" ]]; then
  ./scripts/check_runtime_regression.sh "$E12_RULE_ARTIFACT" \
    --required-confirmed-outcomes 5 \
    --required-total-tasks 9 \
    --expected-planner-type rule
fi

E12_LLM_ARTIFACT="benchmarks/data/simulations/regression-llm-e12-routing-recovery/runtime_subset.json"
if [[ -f "$E12_LLM_ARTIFACT" ]]; then
  ./scripts/check_runtime_regression.sh "$E12_LLM_ARTIFACT" \
    --required-confirmed-outcomes 2 \
    --required-total-tasks 3 \
    --expected-planner-type llm \
    --max-average-estimated-cost-cny 0.02
fi

E14_LLM_ARTIFACT="benchmarks/data/simulations/regression-llm-e14-objective-ledger/runtime_subset.json"
if [[ -f "$E14_LLM_ARTIFACT" ]]; then
  ./scripts/check_runtime_regression.sh "$E14_LLM_ARTIFACT" \
    --required-confirmed-outcomes 1 \
    --required-total-tasks 1 \
    --expected-planner-type llm \
    --max-average-estimated-cost-cny 0.05
fi

E15_LLM_ARTIFACT="benchmarks/data/simulations/regression-llm-e15-locked-order-generalization-v2/runtime_subset.json"
if [[ -f "$E15_LLM_ARTIFACT" ]]; then
  ./scripts/check_runtime_regression.sh "$E15_LLM_ARTIFACT" \
    --required-confirmed-outcomes 2 \
    --required-total-tasks 2 \
    --expected-planner-type llm \
    --max-average-estimated-cost-cny 0.05
fi

E16_LLM_ARTIFACT="benchmarks/data/simulations/regression-llm-e16-structured-write-plan-v3/runtime_subset.json"
if [[ -f "$E16_LLM_ARTIFACT" ]]; then
  ./scripts/check_runtime_regression.sh "$E16_LLM_ARTIFACT" \
    --required-confirmed-outcomes 1 \
    --required-total-tasks 1 \
    --expected-planner-type llm
fi

E17_LLM_ARTIFACT="benchmarks/data/simulations/regression-llm-e17-order-id-recovery/runtime_subset.json"
if [[ -f "$E17_LLM_ARTIFACT" ]]; then
  ./scripts/check_runtime_regression.sh "$E17_LLM_ARTIFACT" \
    --required-confirmed-outcomes 1 \
    --required-total-tasks 1 \
    --expected-planner-type llm \
    --max-failed-order-lookups 0
fi
