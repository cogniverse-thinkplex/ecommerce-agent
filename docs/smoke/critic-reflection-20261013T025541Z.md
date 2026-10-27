# Critic / Reflection Candidate Notes: smoke-pair-20261013T025541Z

## Run Evidence

- Rule artifact: `benchmarks/data/simulations/smoke-rule-20261013T025541Z/runtime_subset.json`
- LLM artifact: `benchmarks/data/simulations/smoke-llm-20261013T025541Z/runtime_subset.json`
- Smoke report: `docs/smoke/smoke-pair-20261013T025541Z.md`
- Command: `ECOM_AGENT_PROPOSAL_LLM=dashscope/qwen3.7-flash ./scripts/run_runtime_smoke_pair.sh --simulations-dir benchmarks/data/simulations --report-dir docs/smoke --max-steps 6`
- Note: `dashscope/deepseek-v4-pro-0813` reached free-tier quota exhaustion during the first real LLM run, so this completed run used `dashscope/qwen3.7-flash`.

## Summary

The rule baseline matched 2 of 3 smoke tasks exactly and stopped at the expected write-operation confirmation gate for tasks 0 and 1. The LLM planner matched 0 of 3 tasks exactly. All LLM failures are currently classified as `planner_terminal`, meaning the planner stopped before producing the next valid tool proposal.

This points to a planner-control problem before deeper tool semantics: the model can select some early read tools, but it does not reliably keep emitting strict JSON tool decisions until the runtime reaches a guard-controlled write proposal.

## Failure Clusters

### Cluster A: Invalid Planner JSON

- Representative task: `0`
- Rule behavior: `find_user_id_by_name_zip -> get_order_details -> get_product_details -> get_product_details -> exchange_delivered_order_items`
- LLM behavior: `find_user_id_by_name_zip`
- Terminal event: `planner.invalid_output`
- Planner message: `Planner output was not valid JSON`

Likely cause: the prompt allows the model to drift back into natural language after the first tool result. The runtime correctly rejects this, but the next prompt should make the JSON-only contract harder to violate.

Candidate changes:

- Add a short hard rule near the end of the LLM planner prompt: every non-terminal step must return exactly one JSON object, with no prose or Markdown.
- Add one valid multi-step example showing that after `find_user_id_by_name_zip`, the next decision should usually be another `tool_call`, not a natural-language response.
- Consider adding a lightweight retry node for `planner.invalid_output` that feeds the invalid text back and asks for JSON repair once before stopping the task.

### Cluster B: Premature Final Response Before Write Proposal

- Representative task: `1`
- Rule behavior: `find_user_id_by_name_zip -> get_order_details -> get_product_details -> get_product_details -> exchange_delivered_order_items`
- LLM behavior: `find_user_id_by_name_zip -> get_order_details -> get_product_details -> get_product_details`
- Terminal event: `planner.final_response`
- Missing next action: `exchange_delivered_order_items`

Likely cause: after collecting enough product details, the model explains or summarizes instead of proposing the guarded write tool. For this benchmark, the correct behavior is to propose the write tool and let the policy guard stop at pending confirmation.

Candidate changes:

- Add a prompt rule: if the user request requires cancellation, return, exchange, or other order mutation and all required read context is present, emit the corresponding write tool proposal instead of a final answer.
- Add skill-level guidance for `exchange_order`: after target item and replacement item are known, route to `exchange_delivered_order_items`; do not finalize before the guard creates pending confirmation.
- In Critic checks, flag any `final_response` that occurs while expected remaining actions include a write tool.

### Cluster C: Need More Info And Extra Product Catalog Lookup

- Representative task: `2`
- Rule behavior: `find_user_id_by_name_zip -> get_product_details`
- LLM behavior: `find_user_id_by_name_zip -> get_user_details -> list_all_product_types -> get_product_details`
- Terminal event: `planner.need_more_info`
- First mismatch index: `1`
- Unexpected action: `list_all_product_types`

Likely cause: the planner is not using task-known product names and expected order-recovery flow efficiently. It asks for more information or browses product types instead of following the required return-order investigation path.

Candidate changes:

- Add a prompt rule: when the user identifies product names or an order context is recoverable from user details, prefer targeted `get_product_details` / order lookup over `list_all_product_types`.
- Add skill guidance for `return_order`: after user identity, gather product details and user order history before asking the user for more information.
- Add a Critic heuristic: `need_more_info` is suspicious if the state already has user identity plus product or order clues from the request.

## Proposed Next Implementation Slice

1. Strengthen the LLM planner prompt output contract and add a one-shot JSON repair path for invalid planner output.
2. Add skill-policy prompt examples for exchange and return flows that demonstrate continuing to a guarded write proposal.
3. Add tests with fake LLM decisions for:
   - invalid JSON repair produces a valid next planner decision;
   - exchange flow does not final-response before write proposal;
   - return flow avoids `list_all_product_types` when the product name is known.
4. Re-run:

```bash
ECOM_AGENT_PROPOSAL_LLM=dashscope/qwen3.7-flash ./scripts/run_runtime_smoke_pair.sh \
  --simulations-dir benchmarks/data/simulations \
  --report-dir docs/smoke \
  --max-steps 6
```

## Regression Gate

Do not treat an LLM planner prompt change as accepted until the smoke pair report shows:

- no `planner.invalid_output` on tasks 0, 1, 2;
- no `planner.final_response` before expected write tools;
- no `planner.need_more_info` when existing context contains enough identity, order, or product clues;
- task 0 and task 1 reach `pending_confirmation` with exact action prefix at least equal to the rule baseline.
