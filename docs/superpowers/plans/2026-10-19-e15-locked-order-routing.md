# E15 Locked-Order Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent fallback and loop-recovery paths from leaving an order locked by a confirmed write, then validate a second independent multi-write task.

**Architecture:** Enforce the Objective Ledger at the runtime proposal boundary. A `get_order_details` proposal for a different order is rewritten to the locked order and recorded as a recovery event; repeated-read recovery may not replace a locked-order read with another order. Planner message context is compacted around the ledger and locked entity.

**Tech Stack:** Python, Pydantic, pytest, tau2 Retail.

**Spec:** `docs/final_implementation_roadmap.md` E15 recommendation.

## Global Constraints

- No benchmark task IDs in runtime logic.
- Never rewrite write-tool arguments; mismatched writes remain blocked by Guard/evaluator.
- Locked-order enforcement applies only after a successful write established the lock.
- Existing unlocked-order discovery remains unchanged.

## Review Focus

- Missing lock leaves proposals unchanged.
- Same-order reads remain valid.
- Different-order reads are rewritten and traced.
- Write calls for a different order are never silently rewritten.
- Multi-order objectives must be able to advance after the current locked objective completes in a future phase.

### Task 1: Locked-Order Runtime Enforcement

- [x] Add failing tests for wrong-order read rewrite, same-order preservation, and write non-rewrite.
- [x] Implement runtime proposal enforcement and recovery event.
- [x] Run focused and full tests.

### Task 2: Multi-Write Generalization

- [x] Run local deterministic checks for task `71` and inspect task `96` fixture.
- [x] Run one real LLM regression containing tasks `71` and `96`.
- [x] Gate confirmed outcomes and measured multi-write cost.

### Task 3: Documentation And Validation

- [x] Add E15 artifact gate without triggering paid calls.
- [x] Update README and roadmap with exact results and remaining limitations.
- [x] Run `./scripts/validate_local.sh`: `225 passed`; all saved E9-E15 artifact gates passed.
