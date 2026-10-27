# P0 tau2 Retail Baseline

Date: 2026-09-14

## Purpose

This baseline verifies that the local tau2 Retail benchmark can run end to end before we build the custom LangGraph customer service agent.

## Local Setup

- Project root: `/Users/chengjiechuan/Desktop/self_file/job/LLM/Code/e-commerce-agent`
- tau2 source/data location: `benchmarks/`
- Conda environment: `ecom-agent`
- Python used by tau2 `.venv`: `3.12.14`
- uv: `0.12.13`
- tau2 package: `1.0.1`

The tau2 project was downloaded directly into `benchmarks/`, not `benchmarks/tau2-bench/`.

## Data Check

Command:

```bash
cd benchmarks
/opt/miniconda3/envs/ecom-agent/bin/uv run tau2 check-data
```

Result:

```text
Data directory: /Users/chengjiechuan/Desktop/self_file/job/LLM/Code/e-commerce-agent/benchmarks/data
Data directory exists
You can now run tau2 commands.
```

Retail data is present at `benchmarks/data/tau2/domains/retail/`, including:

- `db.json`
- `tasks.json`
- `split_tasks.json`
- `policy.md`
- `tasks_voice.json`
- `task_issues/`

## Model Configuration

Provider: Alibaba Cloud Model Studio / DashScope through LiteLLM.

Environment variables in `.env`:

```text
DASHSCOPE_API_KEY=<local secret>
DASHSCOPE_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
TAU2_AGENT_LLM=dashscope/deepseek-v4-pro-0813
TAU2_USER_LLM=dashscope/deepseek-v4-pro-0813
TAU2_NL_ASSERTIONS_LLM=dashscope/deepseek-v4-pro-0813
TAU2_ENV_INTERFACE_LLM=dashscope/deepseek-v4-pro-0813
TAU2_NUM_TASKS=5
TAU2_NUM_TRIALS=1
TAU2_MAX_CONCURRENCY=1
TAU2_SAVE_TO=p0_retail_baseline
```

## tau2 Compatibility Notes

The current tau2 code imports Python's `audioop`, which is unavailable in Python 3.13. The local tau2 virtual environment must use Python 3.12:

```bash
cd benchmarks
/opt/miniconda3/envs/ecom-agent/bin/uv sync --python /opt/miniconda3/envs/ecom-agent/bin/python --extra dev
/opt/miniconda3/envs/ecom-agent/bin/uv pip install "websockets>=13.0"
```

The tau2 CLI imports the voice OpenAI provider even for text runs, so `websockets` is required as a minimal extra dependency.

The tau2 NL assertion evaluator originally hard-coded `DEFAULT_LLM_NL_ASSERTIONS = "gpt-4.1-2025-04-14"`. We made the local downloaded tau2 config read `TAU2_NL_ASSERTIONS_LLM` and `TAU2_ENV_INTERFACE_LLM` from the environment so the baseline can run fully through DashScope without an OpenAI API key.

## Run Command

Command:

```bash
./scripts/run_tau2_retail_baseline.sh
```

Expanded command:

```bash
cd benchmarks
/opt/miniconda3/envs/ecom-agent/bin/uv run tau2 run \
  --domain retail \
  --agent llm_agent \
  --agent-llm dashscope/deepseek-v4-pro-0813 \
  --user-llm dashscope/deepseek-v4-pro-0813 \
  --num-trials 1 \
  --num-tasks 5 \
  --max-concurrency 1 \
  --save-to p0_retail_baseline \
  --auto-resume \
  --log-level INFO
```

## Results

Output file:

```text
benchmarks/data/simulations/p0_retail_baseline_with_cost/results.json
```

Verified result summary:

| Task ID | Reward |
| --- | ---: |
| 0 | 1.0 |
| 1 | 1.0 |
| 2 | 1.0 |
| 3 | 1.0 |
| 4 | 1.0 |

tau2 final metrics:

```text
Total Simulations: 5
Total Tasks: 5
Average Reward: 1.0000
Pass^1: 1.000
Avg Cost/Conversation: $0.1000
Read Actions: 37/40 (92.5%)
Write Actions: 6/6 (100.0%)
DB Match: 5 / 5 (100.0%)
Normal Stop: 5
Agent Errors: 0
User Errors: 0
```

LiteLLM reported cost as `$0.0000` because `dashscope/deepseek-v4-pro-0813` is not mapped in LiteLLM's public model pricing table. This affects cost reporting only; model calls and benchmark execution succeeded.

After P0, we added a local LiteLLM model cost registration for `dashscope/deepseek-v4-pro-0813` in `benchmarks/src/tau2/utils/llm_utils.py`.

Alibaba Cloud's public price for `deepseek-v4-pro-0813` in Beijing/global regions is:

```text
input_busy_hour=9 CNY / 1M tokens
output_busy_hour=27 CNY / 1M tokens
input_off_peak=4.5 CNY / 1M tokens
output_off_peak=13.5 CNY / 1M tokens
```

LiteLLM reports cost with a dollar symbol, so the local configuration uses an approximate USD conversion for busy-hour pricing:

```text
input_cost_per_token=0.000001272
output_cost_per_token=0.000003816
```

The first run, saved under `p0_retail_baseline`, happened before cost registration, so its saved cost fields are `$0.0000`. We reran the same 5-task baseline under `p0_retail_baseline_with_cost`; tau2 now displays cost in the output panel.

Cost summary from `p0_retail_baseline_with_cost/results.json`:

```text
agent_cost=0.499907
user_cost=0.053954
total_cost=0.553862
avg_cost_per_conversation=0.110772
```

This is an estimate for experiment comparison. The actual charge can differ by region, free-trial credit, exchange rate, and peak/off-peak pricing.

## Follow Up

P0 is ready to serve as the comparison baseline for P1. The next development stage is to create the backend skeleton and a LangGraph-based customer service agent that can run against the tau2 Retail adapter.
