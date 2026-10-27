# E17 Order ID Recovery and Write Plan UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate avoidable tau2 Retail order lookup failures caused by model formatting, guide recovery from genuine misses using trusted session state, and expose the structured write plan in the Chinese dashboard.

**Architecture:** Keep canonicalization and recovery in the agent layer, before proposal validation and outside the tau2 adapter. A pure order-ID helper defines the accepted format; the objective ledger records failed reads and trusted user-order candidates; the planner context receives a compact recovery hint. The existing session endpoint supplies the read-only dashboard plan panel.

**Tech Stack:** Python 3.11+, Pydantic, FastAPI, pytest, vanilla JavaScript, HTML, CSS, tau2 Retail runtime.

**Spec:** `docs/superpowers/specs/2026-10-19-e17-order-id-recovery-and-plan-ui-design.md`

## Global Constraints

- Normalize only `get_order_details` proposals and `write_plan` metadata; never normalize write-tool arguments.
- Accept only case-insensitive `#?W` followed by decimal digits and return `#W<digits>`.
- Recovery candidates may come only from the structured plan or successful `get_user_details` output.
- Keep Guard confirmation, fingerprints, policy validation, order locks, and MCP-managed tool execution unchanged.
- Do not add dependencies or a new HTTP endpoint.
- Dashboard copy is Chinese; benchmark data and raw tool names may remain English.

## Review Focus

- A malformed read ID such as `W82-68610` remains unchanged and reaches normal validation/execution instead of being guessed; Task 1 tests this.
- A valid but non-canonical write ID remains unchanged in both proposal and pending confirmation; Task 2 tests this.
- A failed lookup is not added to `inspected_order_ids` and is not repeatedly recommended when a different trusted candidate exists; Tasks 1 and 2 test this.
- A session with no plan, missing session state, or model-authored HTML renders a safe empty/escaped plan panel; Task 3 tests this contract.
- Existing write-plan lock handoff and E9-E16 saved artifact gates remain green; Task 4 runs the complete verification suite.

---

### Task 1: Canonical Order Identity and Trusted Recovery State

**Files:**
- Create: `backend/app/agent/order_identity.py`
- Modify: `backend/app/agent/state.py`
- Create: `backend/tests/agent/test_order_identity.py`
- Modify: `backend/tests/agent/test_state.py`

**Interfaces:**
- Produces: `canonicalize_retail_order_id(value: object) -> str | None`.
- Produces: `ObjectiveLedger.failed_order_ids: list[str]` and `ObjectiveLedger.known_order_ids: list[str]`.
- Produces: `record_tool_execution(...)` behavior that records failed `get_order_details` arguments and extracts canonical order IDs from successful `get_user_details` payloads.
- Consumes: existing immutable Pydantic state update pattern and `record_tool_execution(...)` call sites.

- [ ] **Step 1: Write failing canonicalizer tests**

Add parameterized tests asserting canonical output for `W8268610`, `#w8268610`, whitespace-wrapped canonical input, and unchanged canonical input. Add rejection cases for `8268610`, `W82-68610`, empty string, `None`, and non-string values.

- [ ] **Step 2: Run canonicalizer tests and verify RED**

Run: `cd backend && ../benchmarks/.venv/bin/pytest tests/agent/test_order_identity.py -q`

Expected: collection/import failure because `app.agent.order_identity` does not exist.

- [ ] **Step 3: Implement the pure canonicalizer**

Create `canonicalize_retail_order_id(value: object) -> str | None` using one anchored, case-insensitive regular expression. Do not mutate or stringify non-string input.

- [ ] **Step 4: Run canonicalizer tests and verify GREEN**

Run: `cd backend && ../benchmarks/.venv/bin/pytest tests/agent/test_order_identity.py -q`

Expected: all canonicalizer tests pass.

- [ ] **Step 5: Write failing ledger tests**

Extend state tests to assert:

- an errored `get_order_details` records a canonical failed ID but not an inspected ID;
- duplicate failed IDs are deduplicated in insertion order;
- a malformed failed ID is not recorded as trusted identity;
- successful `get_user_details` extracts canonical IDs from its `orders` collection into `known_order_ids`;
- successful `get_order_details` records a canonical inspected ID and removes it from failed IDs if necessary;
- unrelated failures do not alter order identity state.

- [ ] **Step 6: Run ledger tests and verify RED**

Run: `cd backend && ../benchmarks/.venv/bin/pytest tests/agent/test_state.py -q`

Expected: failures because the ledger fields and error-path recording do not exist.

- [ ] **Step 7: Implement ledger identity tracking**

Add the two list fields to `ObjectiveLedger`. Update `record_tool_execution(...)` so the `get_order_details` error path records only canonical arguments before returning, successful reads canonicalize inspected IDs, and successful `get_user_details` extracts order IDs from list or mapping-shaped `orders` data without treating malformed values as trusted.

- [ ] **Step 8: Run Task 1 tests and verify GREEN**

Run: `cd backend && ../benchmarks/.venv/bin/pytest tests/agent/test_order_identity.py tests/agent/test_state.py -q`

Expected: all Task 1 tests pass.

### Task 2: Runtime Normalization and Plan-Aware Recovery Hint

**Files:**
- Modify: `backend/app/agent/runtime.py`
- Modify: `backend/app/agent/proposal_generator.py`
- Modify: `backend/tests/agent/test_runtime.py`
- Modify: `backend/tests/agent/test_proposal_generator.py`

**Interfaces:**
- Consumes: `canonicalize_retail_order_id(value)` and the ledger fields from Task 1.
- Produces: `_normalize_read_order_proposal(state, proposal) -> tuple[CustomerAgentState, ToolProposal]` in `runtime.py`.
- Produces: canonical plan order IDs from `_initialize_write_plan(...)`.
- Produces: planner context field `ORDER_LOOKUP_RECOVERY` containing `failed_order_ids` and at most one `recommended_order_id` derived from the first pending objective, then uninspected known account orders.

- [ ] **Step 1: Write failing runtime normalization tests**

Add focused runtime tests asserting:

- `get_order_details` with ` W8268610 ` executes as `#W8268610` and emits exactly one `planner.order_id_normalized` event containing original and normalized values;
- already canonical read input produces no normalization event;
- malformed read input is unchanged;
- `modify_pending_order_address` with `W8268610` remains unchanged in the proposal and pending confirmation;
- first-turn plan IDs are canonicalized, malformed plan IDs become `None`, and only canonical IDs can establish a lock.

- [ ] **Step 2: Run runtime normalization tests and verify RED**

Run the named new tests with: `cd backend && ../benchmarks/.venv/bin/pytest tests/agent/test_runtime.py -k 'order_id_normalization or write_plan_canonical' -q`

Expected: assertions fail because proposals and plan IDs are not normalized.

- [ ] **Step 3: Implement proposal and plan normalization**

Call `_normalize_read_order_proposal(...)` after skill routing and before locked-order/repeated-read handling and schema validation. Copy the proposal arguments before changing them and append the audit event only for a changed valid ID. Update `_initialize_write_plan(...)` to store only canonical IDs.

- [ ] **Step 4: Run runtime normalization tests and verify GREEN**

Run the same focused command from Step 2.

Expected: all selected tests pass, including the write non-rewrite assertion.

- [ ] **Step 5: Write failing recovery-context tests**

Extend proposal-generator tests to inspect the LLM user context and assert:

- a failed ID plus a different first pending plan ID recommends the plan ID;
- when the pending objective lacks an ID, the first uninspected and non-failed `known_order_ids` entry is recommended;
- failed and inspected candidates are excluded;
- no trusted candidate yields `recommended_order_id: null`;
- the context explicitly prohibits retrying failed IDs and contains no expected benchmark actions.

Add a sequenced runtime test in which the first lookup fails and verify the second LLM request receives the recovery context without the failed ID being marked inspected.

- [ ] **Step 6: Run recovery tests and verify RED**

Run: `cd backend && ../benchmarks/.venv/bin/pytest tests/agent/test_proposal_generator.py tests/agent/test_runtime.py -k 'recovery or failed_order' -q`

Expected: context assertions fail because `ORDER_LOOKUP_RECOVERY` is absent.

- [ ] **Step 7: Implement deterministic recovery context**

Add a small serializer in `proposal_generator.py` that selects one recommended canonical ID in this order: first pending plan objective, then `known_order_ids`; exclude inspected IDs and, when another candidate exists, failed IDs. Include failed IDs and the recommendation in `_build_llm_planner_user_context(...)`, and add a concise system-prompt rule instructing the planner not to retry a failed lookup without newer trusted evidence.

- [ ] **Step 8: Run Task 2 tests and verify GREEN**

Run: `cd backend && ../benchmarks/.venv/bin/pytest tests/agent/test_proposal_generator.py tests/agent/test_runtime.py tests/agent/test_state.py -q`

Expected: all agent behavior tests pass.

### Task 3: Chinese Structured Write Plan Panel

**Files:**
- Modify: `backend/app/static/dashboard/index.html`
- Modify: `backend/app/static/dashboard/app.js`
- Modify: `backend/app/static/dashboard/styles.css`
- Modify: `backend/tests/api/test_dashboard_static.py`

**Interfaces:**
- Consumes: `GET /sessions/{conversation_id}` response field `objective_ledger.write_plan` and existing trace response.
- Produces: `renderWritePlan(plan)` with empty, current, pending, and completed render states.
- Produces: DOM target `#write-plan-list` inside the existing test console.

- [ ] **Step 1: Write failing dashboard contract tests**

Assert the HTML contains `写操作计划`, `write-plan-list`, and `暂无结构化写操作计划`. Assert JavaScript contains `renderWritePlan`, fetches `/sessions/${encodeURIComponent(conversationId)}` alongside the trace request, defines `当前`, `待处理`, and `已完成`, and routes displayed intent through `escapeHtml`.

- [ ] **Step 2: Run dashboard tests and verify RED**

Run: `cd backend && ../benchmarks/.venv/bin/pytest tests/api/test_dashboard_static.py -q`

Expected: new static contract assertions fail.

- [ ] **Step 3: Implement plan markup, rendering, and styling**

Add the unframed plan subsection above `#trace-list`. Fetch trace and session with `Promise.all`; if only the session request returns 404, render an empty plan while preserving trace behavior. Render the first pending objective as current, subsequent pending objectives as pending, completed objectives as completed, with Chinese labels and a fixed responsive grid. Escape every model- or API-provided string. Add restrained status colors consistent with the existing palette and update the static asset version.

- [ ] **Step 4: Run dashboard tests and verify GREEN**

Run: `cd backend && ../benchmarks/.venv/bin/pytest tests/api/test_dashboard_static.py -q`

Expected: all dashboard contract tests pass.

- [ ] **Step 5: Run focused backend suite**

Run: `cd backend && ../benchmarks/.venv/bin/pytest tests/agent tests/api/test_dashboard_static.py -q`

Expected: focused suite passes with no regressions.

### Task 4: Full Verification and E17 Real-Model Evidence

**Files:**
- Modify: `scripts/validate_local.sh`
- Modify: `docs/final_implementation_roadmap.md`
- Modify: `README.md`
- Create: `docs/smoke/regression-llm-e17-order-id-recovery.md`
- Create: `benchmarks/data/simulations/regression-llm-e17-order-id-recovery/runtime_subset.json`

**Interfaces:**
- Consumes: existing runtime regression CLI and quality-gate scripts.
- Produces: durable E17 artifact/report and an offline gate for its confirmed outcome.

- [ ] **Step 1: Run full offline verification before a paid/provider call**

Run: `./scripts/test_backend.sh`

Expected: complete backend suite passes.

Run: `./scripts/validate_local.sh`

Expected: backend tests and every existing E9-E16 artifact gate pass without an API call.

- [ ] **Step 2: Run task 59 once with the configured text model**

Use the existing runtime regression command with planner `llm`, model `dashscope/qwen3.8-flash`, task `59`, confirmed writes enabled, sufficient max steps, run name `regression-llm-e17-order-id-recovery`, and report path `docs/smoke/regression-llm-e17-order-id-recovery.md`.

Expected: the artifact is complete, confirmed outcome is `1/1`, both intended writes execute, no `get_order_details` entry ends with `Order not found`, and tool step count is at most seven. If provider behavior causes a different unrelated path, preserve the complete artifact, diagnose it from trace evidence, repair only a demonstrated product defect through a fresh red-green cycle, and rerun under a `-v2` suffix.

- [ ] **Step 3: Add and prove the E17 offline artifact gate**

Add `check_runtime_regression.sh` invocation for the successful E17 artifact to `validate_local.sh`, requiring planner `llm`, one total task, one confirmed outcome, and no cost ceiling when provider pricing is untrusted. Add a small artifact assertion or extend the gate to reject any E17 task trace containing a failed `get_order_details` lookup.

Run: `./scripts/validate_local.sh`

Expected: all tests and E9-E17 gates pass without a new provider request.

- [ ] **Step 4: Update durable project documentation**

Record the implementation, exact verification counts, model, tokens/cost availability, artifact paths, task 59 action sequence, and any residual risk in `README.md` and `docs/final_implementation_roadmap.md`. Do not claim the seven-step target if the artifact does not demonstrate it.

- [ ] **Step 5: Perform final independent review**

Review the complete diff for write-argument mutation, benchmark-answer leakage, unsafe HTML, inconsistent Pydantic state, and untested error paths. Re-run any affected focused tests after fixes, then run `./scripts/validate_local.sh` one final time.

