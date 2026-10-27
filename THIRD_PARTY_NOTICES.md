# Third-party notices

## tau2-bench

This repository vendors selected source files and the Retail demo fixtures from:

- Project: `tau2-bench`
- Upstream: https://github.com/sierra-research/tau2-bench
- Copyright: Copyright (c) 2025 Sierra Research
- License: MIT
- Local license copy: [benchmarks/LICENSE](benchmarks/LICENSE)

The vendored copy is used as the benchmark environment and Retail tool/data
backend. It is not presented as original work of this repository.

### Local modifications

The local copy contains project-specific changes in these upstream-derived files:

- `benchmarks/src/tau2/utils/llm_utils.py`
- `benchmarks/src/tau2/utils/display.py`
- `benchmarks/src/tau2/scripts/review_conversation.py`
- `benchmarks/tests/test_voice/test_usage_pricing.py`

These changes add or verify model usage and cost metadata for locally configured
LiteLLM/DashScope models and expose that information in the tau2 output panel.
The surrounding e-commerce product, Agent Runtime, MCP adapter, policy guard,
web interfaces, persistence, RAG, regression and operations code live outside
the vendored upstream package.

### Data included in this repository

Only `benchmarks/data/tau2/domains/retail/` is intended to be committed. It is
synthetic benchmark/demo data required by the local product. Official result
archives, other domains, generated simulations and voice data are excluded.

To obtain the full current upstream project and datasets:

```bash
git clone https://github.com/sierra-research/tau2-bench.git
```

When updating the vendored copy, review the upstream license again and reapply
the local modifications explicitly.

## Model and API dependencies

The project can call third-party model providers through LiteLLM-compatible
APIs. Model weights, downloaded embedding caches, API keys and provider output
are not included. Users must review the license and terms of each model/provider
they configure.

