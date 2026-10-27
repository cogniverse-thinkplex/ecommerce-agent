# Critic / Reflection Candidate Notes: smoke-pair-20261013T111309Z

## Run Evidence

- Rule artifact: `benchmarks/data/simulations/smoke-rule-20261013T111309Z/runtime_subset.json`
- LLM artifact: `benchmarks/data/simulations/smoke-llm-20261013T111309Z/runtime_subset.json`
- Smoke report: `docs/smoke/smoke-pair-20261013T111309Z.md`
- Command: `ECOM_AGENT_PROPOSAL_LLM=dashscope/qwen3.7-flash ./scripts/run_runtime_smoke_pair.sh --simulations-dir benchmarks/data/simulations --report-dir docs/smoke --max-steps 6`

## Summary

This run validates the E5 runtime-control changes. Regressions against the rule baseline are now `0`, and LLM exact match is `2/3`, matching the rule baseline on the fixed smoke set.

Tasks 0 and 1 both reached the same action sequence as the rule baseline:

`find_user_id_by_name_zip -> get_order_details -> get_product_details -> get_product_details -> exchange_delivered_order_items`

The remaining non-exact task is task 2. This is also non-exact for the rule baseline, but the LLM still takes a noisier path:

`find_user_id_by_name_zip -> get_user_details -> list_all_product_types -> get_product_details`

## What Improved

- Task 1 no longer loops on repeated user/order lookup before the exchange write proposal.
- Smoke comparison now reports `regressions=0`.
- The planner-control layer can recover from repeated read proposals and unknown tool names in unit tests.
- A diagnostic priority fix ensures future artifacts classify exact-match pending confirmation as `pending_confirmation` rather than letting incidental rejection events dominate the failure category.

## Remaining Failure Cluster

### Task 2: Return Flow Still Uses Catalog Browsing

- Representative task: `2`
- Rule behavior: `find_user_id_by_name_zip -> get_product_details`
- LLM behavior: `find_user_id_by_name_zip -> get_user_details -> list_all_product_types -> get_product_details`
- Baseline comparison status: `unchanged`
- First mismatch index: `1`

Likely cause: the return flow lacks a deterministic policy for known product clues. The planner still tries to discover catalog/product context broadly, instead of following a targeted return-order investigation path.

Candidate changes:

- Add skill examples for `return_order` that start from product clues and user order history.
- Add a targeted fallback for return flows: when user identity and known product name are available, prefer `get_product_details` for the named product before broad catalog lookup.
- Add a loop/selection guard that discourages `list_all_product_types` when the user message already contains a product name.

## Proposed Next Implementation Slice

1. Add return-flow deterministic routing for known product names.
2. Add prompt examples for return scenarios that require finding relevant delivered orders before proposing `return_delivered_order_items`.
3. Add fake LLM tests proving `list_all_product_types` is replaced or rejected when a known product clue exists.
4. Re-run:

```bash
ECOM_AGENT_PROPOSAL_LLM=dashscope/qwen3.7-flash ./scripts/run_runtime_smoke_pair.sh \
  --simulations-dir benchmarks/data/simulations \
  --report-dir docs/smoke \
  --max-steps 6
```

## Regression Gate

Do not accept the next return-flow change until:

- task 0 and task 1 remain exact match and reach `pending_confirmation`;
- task 2 avoids `list_all_product_types` when the product name is known;
- smoke comparison keeps `regressions=0`.
