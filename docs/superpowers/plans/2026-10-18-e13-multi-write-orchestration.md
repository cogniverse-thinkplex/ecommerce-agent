# E13 Multi-Write Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Continue one customer objective across multiple independently confirmed write operations and verify every expected mutation.

**Architecture:** Keep Guard as the sole authorization boundary. Add a session-service operation that confirms and executes exactly the current pending action, then resumes the original objective. The evaluation runner may repeat this operation only when the pending tool and arguments exactly match an expected write action; it never gives expected actions to the planner.

**Tech Stack:** Python, FastAPI, Pydantic, pytest, tau2 Retail adapter.

**Spec:** `docs/final_implementation_roadmap.md` section "阶段 E 第十二轮" and its E13 recommendation.

## Global Constraints

- Do not branch on benchmark task IDs.
- Every write keeps its own Guard confirmation fingerprint.
- Never auto-confirm a write whose complete arguments differ from the expected action.
- Existing single-write API and evaluation behavior stays compatible.

## Review Focus

- Rejected confirmations must not execute or continue.
- A changed proposal after confirmation must require a new confirmation.
- Incorrect intermediate writes must stop without mutating state.
- Step and confirmation-cycle budgets must terminate deterministically.
- Multi-write success requires all expected writes, not only the last write.

### Task 1: Confirm And Continue Service

**Files:**
- Modify: `backend/app/agent/session_service.py`
- Modify: `backend/app/api/main.py`
- Test: `backend/tests/agent/test_session_service.py`
- Test: `backend/tests/api/test_agent_runtime_api.py`

- [x] Write failing tests for confirmed execution followed by resumed planning and rejection without execution.
- [x] Run the focused tests and verify the missing interface fails.
- [x] Add the service result model, method, request model, and API route.
- [x] Run the focused tests and verify they pass.

### Task 2: Multi-Write Evaluation Loop

**Files:**
- Modify: `backend/app/evaluation/runtime_task_runner.py`
- Modify: `backend/app/evaluation/outcome_evaluator.py`
- Test: `backend/tests/evaluation/test_runtime_task_runner.py`
- Test: `backend/tests/evaluation/test_outcome_evaluator.py`

- [x] Write failing tests for two sequential writes, wrong intermediate arguments, and complete multi-write outcome verification.
- [x] Run focused tests and verify the intended failures.
- [x] Implement bounded confirmation cycles and execution evidence for every expected write.
- [x] Run focused and complete backend tests.

### Task 3: E13 Regression And Documentation

**Files:**
- Modify: `backend/app/evaluation/runtime_regression.py`
- Modify: `scripts/validate_local.sh`
- Modify: `README.md`
- Modify: `docs/final_implementation_roadmap.md`
- Create: `docs/smoke/regression-llm-e13-multi-write.md`

- [x] Run the local rule diagnostic.
- [x] Run only task `71` with the configured LLM and persist both diagnostic artifacts.
- [x] Keep failed E13 diagnostics out of the success gate; unit tests enforce the orchestration contract.
- [x] Run `./scripts/validate_local.sh`: `219 passed`; all E9-E12 saved-artifact gates passed.
