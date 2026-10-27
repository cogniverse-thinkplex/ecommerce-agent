# E16 Structured Write Plan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a guarded, structured multi-write plan that advances only from successful real tool executions and supports sequential cross-order objectives.

**Architecture:** Extend planner decisions with optional write objectives, validate them against the live tool catalog, and store a normalized ordered plan in `ObjectiveLedger`. Runtime execution remains authoritative: successful writes complete one matching objective and hand off or release the active order lock; planner context exposes only the next pending objective plus compact plan state.

**Tech Stack:** Python 3.12, Pydantic, pytest, tau2 Retail, FastAPI service layer.

**Spec:** `docs/superpowers/specs/2026-10-19-e16-structured-write-plan-design.md`

## Global Constraints

- Never read benchmark task IDs or expected actions in planner/runtime code.
- Never use the write plan to generate, rewrite, confirm, or execute write arguments.
- Only successful guarded write execution may mark an objective complete.
- Unknown and read-only planned tools are discarded.
- Plan entries always start pending; LLM-supplied completion state is ignored.
- Preserve duplicate tool objectives and declared order.
- Cap accepted plan entries at eight.
- Existing sessions without a plan retain E15 behavior.

## Review Focus

- Malformed or partially valid plans retain valid write entries without crashing.
- Duplicate write tools complete one entry per successful execution.
- A failed write or rejected confirmation leaves plan and order lock unchanged.
- Cross-order objectives hand off the lock only after current-objective success.
- Tool proposals and confirmation fingerprints remain byte-for-byte independent of plan metadata.

---

### Task 1: Planner And State Contract

**Files:**
- Modify: `backend/app/agent/state.py`
- Modify: `backend/app/agent/proposal_generator.py`
- Test: `backend/tests/agent/test_state.py`
- Test: `backend/tests/agent/test_proposal_generator.py`

**Interfaces:**
- Produces: `WriteObjective`, `ObjectiveLedger.write_plan`, `PlannerDecision.write_plan`.
- Consumes: existing `RetailToolDefinition` catalog and planner JSON parser.

- [x] Add failing tests for parsing an optional plan, duplicate tool entries, ignored supplied status, and planner context containing `NEXT_WRITE_OBJECTIVE`.
- [x] Add `WriteObjective` and the optional planner decision payload without changing existing decision shapes.
- [x] Render compact plan and next pending objective in planner context.
- [x] Run focused parser/state tests and then the complete proposal-generator tests: `47 passed`.

### Task 2: Runtime Plan Validation

**Files:**
- Modify: `backend/app/agent/runtime.py`
- Modify: `backend/app/agent/state.py`
- Test: `backend/tests/agent/test_runtime.py`
- Test: `backend/tests/agent/test_state.py`

**Interfaces:**
- Produces: `initialize_write_plan(state, raw_plan, tools) -> CustomerAgentState` and `objective_plan.created` trace event.
- Consumes: `PlannerDecision.write_plan` and executor `list_tools()`.

- [x] Add failing tests for valid plan normalization, unknown/read-only filtering, eight-entry cap, and immutable existing plan.
- [x] Validate the first supplied plan against live write tools and assign unique normalized IDs.
- [x] Store the plan before routing the decision's tool proposal and emit a compact creation event.
- [x] Verify malformed plans leave runtime behavior unchanged: runtime tests `27 passed`.

### Task 3: Trusted Completion And Lock Handoff

**Files:**
- Modify: `backend/app/agent/state.py`
- Modify: `backend/app/agent/nodes/tool_node.py` only if event payload needs plan progress metadata.
- Test: `backend/tests/agent/test_state.py`
- Test: `backend/tests/agent/test_tool_node.py`

**Interfaces:**
- Produces: completion matching inside `record_tool_execution` and derived next-objective order lock.
- Consumes: successful write name, arguments, and fingerprint from guarded execution.

- [x] Add failing tests for single-item completion, duplicate first-pending completion, mismatch/no advancement, failure/no advancement, same-order lock retention, cross-order handoff, and unknown-order lock release.
- [x] Complete only the first matching pending objective after a successful write.
- [x] Store the actual fingerprint and derive `locked_order_id` from the next pending objective.
- [x] Keep existing completed-write recording unchanged for sessions without a plan.
- [x] Run state, tool-node, runtime, and session-service tests: `46 passed`.

### Task 4: Continuation Contract

**Files:**
- Modify: `backend/app/agent/session_service.py`
- Modify: `backend/app/agent/proposal_generator.py`
- Test: `backend/tests/agent/test_session_service.py`
- Test: `backend/tests/agent/test_proposal_generator.py`

**Interfaces:**
- Produces: ledger-driven continuation prompt and explicit next-objective planner instruction.
- Consumes: `ObjectiveLedger.write_plan` and `NEXT_WRITE_OBJECTIVE` context.

- [x] Add failing tests proving continuation uses original objective, names the next structured objective, and does not restate completed write arguments.
- [x] Replace free-form completed-write continuation with a compact ledger-driven directive.
- [x] Instruct the planner to resolve and propose only the next pending write objective.
- [x] Verify Guard confirmation and pending action arguments remain unchanged: focused suite `91 passed`.

### Task 5: Regression And Documentation

**Files:**
- Modify: `scripts/validate_local.sh`
- Modify: `README.md`
- Modify: `docs/final_implementation_roadmap.md`
- Create: `docs/smoke/regression-llm-e16-structured-write-plan.md`
- Create: `benchmarks/data/simulations/regression-llm-e16-structured-write-plan/runtime_subset.json`

**Interfaces:**
- Consumes: tau2 Retail task `59`, runtime subset runner, and saved-artifact quality gate.
- Produces: one reproducible E16 acceptance artifact and offline gate.

- [x] Run the full backend test suite and all saved E9-E15 gates before the paid check: `233 passed` before the check; later fixes reached `235 passed`.
- [x] Run bounded real task `59` diagnostics: v1 exposed missing plans; v2 created a two-item plan and exposed order-read false loop detection.
- [x] Require all expected writes and state change evidence: qwen3.8-flash v3 reached `1/1` confirmed outcome with both writes executed. The `CNY 0.05` directory-price assertion remains unavailable because this new model has no configured trusted price.
- [x] Retain v1/v2 as diagnostics and add only successful v3 to the E16 offline business-result gate.
- [x] Update README and roadmap with measured diagnostics, quota limitation, and the next recommendation.
- [x] Run final `./scripts/validate_local.sh`: `235 passed, 1 warning`; all saved E9-E15 artifact gates passed.
