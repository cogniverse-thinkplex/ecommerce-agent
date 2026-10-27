# E10 Rule vs LLM Representative Regression

## Result

| Planner | Model | Confirmed outcome | Exact match | Avg steps | Input tokens | Output tokens | Estimated list cost |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Rule | deterministic | 5/5 | 2/5 | 5.40 | 0 | 0 | CNY 0 |
| LLM | qwen3.7-flash | 5/5 | 2/5 | 5.40 | 155,768 | 29,965 | CNY 0.055126 |

The LLM run reached the same confirmed business outcomes as the rule baseline.
Its average estimated list cost was CNY 0.011025 per task. The provider did not
return a verifiable billed amount, so this is an estimate from observed token
usage and the published Alibaba Cloud list price, not an invoice amount.

## Behavioral Differences

- Exchange and payment update matched the expected action sequence exactly.
- Return reached the 10-step budget and recovered from known-product, rejected
  tool, and repeated-read planner decisions before completing the write.
- Cancel and address update reached the correct write through generic fallback
  paths. No task ID shortcuts were used.
- Because both planners already reached 5/5, E10 did not tune the prompt against
  this five-task set. The preserved baseline is more useful for detecting future
  regressions than an overfit prompt change.

## Quality Gate

```bash
./scripts/check_runtime_regression.sh \
  benchmarks/data/simulations/regression-rule-e9-write-workflows/runtime_subset.json \
  --required-confirmed-outcomes 5 \
  --expected-planner-type rule

./scripts/check_runtime_regression.sh \
  benchmarks/data/simulations/regression-llm-e10-qwen37-flash-usage/runtime_subset.json \
  --required-confirmed-outcomes 5 \
  --expected-planner-type llm \
  --max-average-estimated-cost-cny 0.02
```

Both gates pass. The initial DeepSeek attempt is not represented as a benchmark
result because the provider rejected the first request after its free quota was
exhausted; no runtime artifact was produced.
