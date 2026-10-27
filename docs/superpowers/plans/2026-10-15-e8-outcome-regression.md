# E8 Outcome Regression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add parameter-aware, post-confirmation business outcome validation and a representative Retail regression suite with scenario metrics.

**Architecture:** Keep trajectory comparison in `session_task_check`, but delegate target-write validation to a focused outcome evaluator. The runtime runner may execute a correctly matched pending write in its isolated tau2 environment, record execution and database-change evidence, and aggregate scenario-level metrics from a declarative regression manifest.

**Tech Stack:** Python 3.12, Pydantic, pytest, tau2 Retail adapter, FastAPI static dashboard.

**Spec:** `docs/final_implementation_roadmap.md` section “阶段 E 第八轮”.

## Global Constraints

- Do not special-case planner behavior by task id.
- A write action is successful only when its tool name and complete expected arguments match.
- Post-confirmation verification must run only in the task runner's isolated backend.
- Do not estimate model cost when provider usage metadata is unavailable.
- Preserve backward compatibility for older runtime artifacts.

## Review Focus

- Correct tool with wrong arguments must fail business validation.
- A matching pending action must not claim persisted state before confirmation.
- Tool execution errors or unchanged database state must fail confirmed validation.
- Read-only or no-action tasks must report not applicable rather than false success.
- Legacy artifacts without outcome fields must still load and summarize.

---

### Task 1: Parameter-Aware Outcome Evaluator

**Files:**
- Create: `backend/app/evaluation/outcome_evaluator.py`
- Modify: `backend/app/evaluation/session_task_check.py`
- Test: `backend/tests/evaluation/test_outcome_evaluator.py`

- [x] Write failing tests for matching arguments, wrong arguments, missing pending action, and no expected write action.
- [x] Run focused tests and confirm the expected failures.
- [x] Implement `BusinessOutcomeCheck` and pending-action evaluation.
- [x] Run focused tests until green.

### Task 2: Confirmed Execution Evidence

**Files:**
- Modify: `backend/app/tools/guarded_executor.py`
- Modify: `backend/app/evaluation/runtime_task_runner.py`
- Test: `backend/tests/evaluation/test_runtime_task_runner.py`

- [x] Write failing integration tests for successful confirmation plus database change and for mismatched arguments not being executed.
- [x] Run focused tests and confirm the expected failures.
- [x] Add optional database hash access and `verify_outcome_execution` runner behavior.
- [x] Persist execution, state-change, step-count, and outcome evidence in artifacts.
- [x] Run focused tests until green.

### Task 3: Representative Scenario Suite

**Files:**
- Create: `backend/app/evaluation/runtime_regression.py`
- Create: `scripts/run_runtime_regression.sh`
- Modify: `backend/app/evaluation/runtime_task_runner.py`
- Test: `backend/tests/evaluation/test_runtime_regression.py`

- [x] Write failing tests for the exchange, return, cancel, address-update, and payment-update manifest.
- [x] Add scenario aggregation for business success, exact match, average steps, and explicit cost.
- [x] Add CLI report generation and run the deterministic rule baseline.
- [x] Verify current supported and unsupported capability results are represented honestly.

### Task 4: Dashboard And Documentation

**Files:**
- Modify: `backend/app/static/dashboard/app.js`
- Modify: `backend/tests/api/test_dashboard_static.py`
- Modify: `README.md`
- Modify: `docs/final_implementation_roadmap.md`
- Create: `docs/smoke/critic-reflection-e8-outcome-regression.md`

- [x] Add outcome evidence and scenario metrics to the existing artifact detail UI.
- [x] Add static UI assertions.
- [x] Document commands, metric meanings, baseline evidence, and remaining capability gaps.
- [x] Run the full backend suite, Python compile check, JavaScript syntax check, and artifact assertions.
