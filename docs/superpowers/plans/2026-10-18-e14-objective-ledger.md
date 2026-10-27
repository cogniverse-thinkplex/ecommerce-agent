# E14 Objective Ledger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve trusted objective progress and resolved entities across planner continuation turns.

**Architecture:** Add a deterministic ledger to `CustomerAgentState`. Runtime initializes the original objective; successful tool calls update inspected entities and completed writes; the LLM receives a compact serialized ledger and must honor a locked order after a completed write.

**Tech Stack:** Python, Pydantic, FastAPI, pytest.

**Spec:** `docs/final_implementation_roadmap.md` E14 recommendation.

## Global Constraints

- Ledger facts come from runtime and tool results, never from LLM self-report.
- Do not use benchmark task IDs or expected actions.
- A completed write locks its `order_id` for remaining work in the same objective.
- Existing state payloads remain backward compatible through defaults.

## Review Focus

- Malformed tool JSON must not corrupt the ledger.
- Failed tool calls must not be recorded as completed writes.
- Repeated reads and writes must be deduplicated.
- A new session starts with an empty ledger.
- Planner context must remain compact and JSON serializable.

### Task 1: Ledger State And Deterministic Updates

- [x] Add failing state/tool-node tests for objective initialization, inspected entities, completed writes, locking, failures, and deduplication.
- [x] Implement ledger models and update helpers.
- [x] Run focused tests.

### Task 2: Runtime And Planner Integration

- [x] Add failing tests proving auto-run initializes the ledger and planner context contains `OBJECTIVE_LEDGER`.
- [x] Integrate objective initialization and compact ledger serialization.
- [x] Strengthen planner instructions for completed writes and locked orders.
- [x] Run focused tests: `70 passed`.

### Task 3: Regression And Documentation

- [x] Run the complete local validation suite: `222 passed` before the final artifact gate addition.
- [x] Run task `71` once; both writes completed and database state changed.
- [x] Document measured behavior, cost, and remaining gaps.
