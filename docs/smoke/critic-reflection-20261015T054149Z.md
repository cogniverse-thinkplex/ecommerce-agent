# Critic / Reflection Candidate Notes: smoke-pair-20261015T054149Z

## Run Evidence

- Rule artifact: `benchmarks/data/simulations/smoke-rule-20261015T054149Z/runtime_subset.json`
- LLM artifact: `benchmarks/data/simulations/smoke-llm-20261015T054149Z/runtime_subset.json`
- Smoke report: `docs/smoke/smoke-pair-20261015T054149Z.md`
- Command: `ECOM_AGENT_PROPOSAL_LLM=dashscope/qwen3.7-flash ./scripts/run_runtime_smoke_pair.sh --simulations-dir benchmarks/data/simulations --report-dir docs/smoke --max-steps 6`

## Summary

This run validates the E6 known-product and return-flow controls. LLM exact match remains `2/3`, matching the rule baseline, with `regressions=0`.

Tasks 0 and 1 remain exact and reach pending confirmation:

`find_user_id_by_name_zip -> get_order_details -> get_product_details -> get_product_details -> exchange_delivered_order_items`

Task 2 now starts with the intended business sequence:

`find_user_id_by_name_zip -> get_product_details -> get_user_details -> get_order_details`

Neither `list_all_product_types` nor `transfer_to_human_agents` appears in the accepted run.

## Changes Validated

- A known T-Shirt clue replaces broad account/catalog discovery with targeted product details.
- Return planning can retrieve the authenticated user's order list and inspect unchecked orders deterministically.
- Unknown tools prefer an available deterministic next action before invoking LLM repair.
- The first E6 smoke (`20261015T053240Z`) exposed a stochastic task 1 regression through an unnecessary handoff; the accepted rerun confirms that regression is removed.
- A separate rule-runtime check with `max_steps=10` reached `return_delivered_order_items` pending confirmation on task 2.

## Remaining Evaluation Gap

Task 2 remains non-exact for both planners. Its generated reference trajectory contains two `get_product_details` actions, including an initial lookup for product id `6086499569`, which is absent from the current product database. The implemented flow does not reproduce this invalid lookup merely to improve action-prefix scoring.

At `max_steps=6`, the long return flow also ends before all five orders can be inspected. This is a step-budget limitation, not a missing deterministic transition.

The accepted LLM artifact still records two recovered invalid skill annotations. Follow-up local changes normalize these cases, with focused tests plus the full backend suite passing; no additional paid smoke was run because tool-selection behavior did not otherwise change.

## Verification

- Full backend suite: `171 passed`, one existing tau2 `audioop` deprecation warning.
- Agent suite: `78 passed` before the final skill-normalization slice.
- Python compile check: passed.
- Real smoke: LLM exact `2/3`, regressions `0`, improvements `0`.
- Task 2 catalog/handoff scan: no matches for `list_all_product_types` or `transfer_to_human_agents`.

## Proposed Next Implementation Slice

1. Separate business-outcome success from strict generated action-sequence matching.
2. Add a longer return-flow smoke with a task-specific step budget.
3. Treat recovered planner rejections as recovery diagnostics rather than terminal failure categories.
4. Keep paid smoke runs for planner behavior changes; use deterministic replay for output-normalization changes.
