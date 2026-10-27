# Critic / Reflection Candidate Notes: smoke-pair-20261013T030935Z

## Run Evidence

- Rule artifact: `benchmarks/data/simulations/smoke-rule-20261013T030935Z/runtime_subset.json`
- LLM artifact: `benchmarks/data/simulations/smoke-llm-20261013T030935Z/runtime_subset.json`
- Smoke report: `docs/smoke/smoke-pair-20261013T030935Z.md`
- Command: `ECOM_AGENT_PROPOSAL_LLM=dashscope/qwen3.7-flash ./scripts/run_runtime_smoke_pair.sh --simulations-dir benchmarks/data/simulations --report-dir docs/smoke --max-steps 6`

## Summary

This run validates the E4 planner-control changes. Compared with the prior completed LLM smoke run, exact match improved from `0/3` to `1/3`, and regressions against the rule baseline dropped from `2` to `1`.

Task 0 now reaches the same guarded write proposal as the rule baseline:

`find_user_id_by_name_zip -> get_order_details -> get_product_details -> get_product_details -> exchange_delivered_order_items`

The remaining failures are no longer dominated by `planner_terminal`. They have shifted to repeated action loops and tool-schema/tool-name rejection, which is the right next layer to address.

## Failure Clusters

### Cluster A: Repeated Read Actions Before Write Proposal

- Representative task: `1`
- Rule behavior: `find_user_id_by_name_zip -> get_order_details -> get_product_details -> get_product_details -> exchange_delivered_order_items`
- LLM behavior: `find_user_id_by_name_zip -> get_order_details -> get_product_details -> get_product_details -> find_user_id_by_name_zip -> get_order_details`
- Failure category: `action_deviation`
- Stop reason: `max_steps`
- First mismatch index: `4`

Likely cause: the planner does not treat already-collected user and order context as authoritative enough. After enough exchange context exists, it restarts authentication/order lookup instead of proposing the guarded exchange write.

Candidate changes:

- Add a loop guard that rejects or rewrites identical read tool calls when their result is already present in recent state.
- Add prompt guidance: do not repeat `find_user_id_by_name_zip` or `get_order_details` if the same user/order result is already in recent messages.
- Add a deterministic write-proposal fallback when an exchange task has order details and replacement product details but the planner proposes a repeated read.

### Cluster B: Unknown Tool Rejection In Return Flow

- Representative task: `2`
- LLM behavior: `find_user_id_by_name_zip -> get_user_details -> list_all_product_types -> get_product_details`
- Failure category: `rejected`
- Rejection kind: `tool_proposal.rejected`
- Rejection reason: `unknown_tool`

Likely cause: the model is still browsing the product catalog and may emit tool names outside `AVAILABLE_TOOLS` when it gets uncertain. The system prompt now discourages `list_all_product_types`, but task 2 still needs stronger return-flow examples and a rejection-repair path.

Candidate changes:

- Add a rejection repair node for `unknown_tool`: feed the rejected tool name and `AVAILABLE_TOOLS` back once and ask for a valid replacement.
- Add a return-flow example that uses known product clues and user order history rather than catalog browsing.
- Consider a hard policy in validation: if product name is already known, reject `list_all_product_types` with a targeted reason and let repair choose `get_product_details`.

## Proposed Next Implementation Slice

1. Add repeated-read detection before tool execution.
2. Add a deterministic exchange fallback when the planner repeats user/order lookup after all exchange prerequisites are already present.
3. Add one-shot repair for `unknown_tool` rejections in LLM runtime.
4. Add fake LLM tests for repeated read suppression and unknown tool repair.
5. Re-run:

```bash
ECOM_AGENT_PROPOSAL_LLM=dashscope/qwen3.7-flash ./scripts/run_runtime_smoke_pair.sh \
  --simulations-dir benchmarks/data/simulations \
  --report-dir docs/smoke \
  --max-steps 6
```

## Regression Gate

Do not accept the next planner-control change until:

- task 0 remains exact match and reaches `pending_confirmation`;
- task 1 reaches `exchange_delivered_order_items` instead of repeating user/order lookup;
- no smoke task fails with `unknown_tool`;
- regressions against rule baseline are `0` for tasks 0 and 1.
