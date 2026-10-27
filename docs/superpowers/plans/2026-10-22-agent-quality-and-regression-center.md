# Agent Quality and Regression Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fragmented developer Dashboard with a six-module engineering console that records Agent telemetry, reports system quality, and turns production issues, feedback, and failed runs into replayable regression cases.

**Architecture:** Add normalized SQLite run and regression records beneath focused repositories and services. Instrument the existing session/runtime and evaluation boundaries through one telemetry service, expose developer-only quality/run/regression/system APIs, then rebuild the Dashboard navigation around those APIs while retaining compatibility endpoints for scripts and tests.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, stdlib `sqlite3`, tau2 Retail, MCP Python SDK, vanilla JavaScript/HTML/CSS, pytest, Playwright-compatible UI validation.

**Spec:** `docs/superpowers/specs/2026-10-22-agent-quality-and-regression-center-design.md`

## Global Constraints

- Keep the standalone customer support center and its customer-visible API behavior unchanged.
- Developer quality, run, regression, issue, feedback, and system APIs require the `developer` role.
- Never persist API keys, cookies, authorization headers, passwords, complete payment details, or unredacted model reasoning.
- Missing Token usage or pricing remains `NULL`; Rule Planner is labeled “未调用模型” rather than zero cost.
- A waiting confirmation is not a failed run.
- Keep SQLite WAL mode, foreign keys, explicit transactions, and migration ordering.
- Keep MCP as the local product tool backend; no silent fallback to the in-process tau2 adapter.
- Remove arbitrary browser tool execution and fixed task demo controls from the formal Dashboard, but retain compatible backend APIs where tests and scripts use them.
- No new frontend package manager or runtime dependency.
- The repository currently has no `.git` metadata; replace commit checkpoints with updates to the existing SDD progress ledger unless Git becomes available.

## Review Focus

- A process that crashes after creating a `running` row must not permanently inflate live-run counts; Task 2 adds stale-run recovery tests.
- Concurrent requests updating one run must preserve step ordering and final counters; Task 2 adds transaction and sequence tests.
- Unsupported model pricing must remain unknown while Token counts remain available; Task 3 adds mixed-availability aggregation tests.
- A captured issue or feedback with insufficient replay data must create a draft, never an active misleading test; Task 5 adds conversion validation tests.
- Empty time windows and percentile samples of one item must return stable zero/null metrics without division errors; Task 3 adds empty and singleton tests.

---

## File Structure

### Persistence and domain

- Create `backend/app/persistence/migrations/004_agent_quality_regression.sql`: telemetry and regression schema.
- Modify `backend/app/persistence/models.py`: persisted run, step, regression case, and case-run models.
- Modify `backend/app/persistence/sqlite.py`: focused repositories and unit-of-work properties.
- Create `backend/app/telemetry/models.py`: API/domain models for run lifecycle and quality queries.
- Create `backend/app/telemetry/service.py`: run lifecycle, step timing, stale-run recovery, and issue linkage.
- Create `backend/app/telemetry/quality.py`: pure aggregation and percentile functions.
- Create `backend/app/regression/models.py`: case, expectation, batch, and result models.
- Create `backend/app/regression/service.py`: case lifecycle, source conversion, and batch execution.

### Integration and APIs

- Modify `backend/app/agent/session_service.py`: wrap customer and sandbox auto-runs in telemetry lifecycle calls.
- Modify `backend/app/agent/runtime.py`: expose step completion data without changing policy behavior.
- Modify `backend/app/evaluation/runtime_task_runner.py`: emit benchmark/regression telemetry and reusable case results.
- Modify `backend/app/observability/service.py`: link issues/feedback to regression cases and verified resolution.
- Create `backend/app/api/quality.py`: overview, trend, tool, and run endpoints.
- Create `backend/app/api/regression.py`: case conversion, case management, and batch endpoints.
- Create `backend/app/api/system.py`: consolidated runtime/data health endpoint.
- Modify `backend/app/api/main.py`: dependency wiring and router registration.

### Dashboard

- Modify `backend/app/static/dashboard/index.html`: six-module structure and tab containers.
- Modify `backend/app/static/dashboard/styles.css`: responsive quality, run, regression, and system layouts.
- Modify `backend/app/static/dashboard/app.js`: routing/bootstrap only plus compatibility handlers still needed by retained views.
- Create `backend/app/static/dashboard/quality.js`: quality metrics and trend rendering.
- Create `backend/app/static/dashboard/runs.js`: session/run list and detail rendering.
- Create `backend/app/static/dashboard/regression.js`: execution, cases, history, and sandbox tabs.
- Create `backend/app/static/dashboard/operations.js`: issues, feedback, and conversion actions.
- Create `backend/app/static/dashboard/system.js`: system health and developer management.
- Create `backend/app/static/dashboard/api.js`: authenticated JSON request and error normalization.

### Tests and documentation

- Create `backend/tests/persistence/test_quality_regression_repositories.py`.
- Create `backend/tests/telemetry/test_telemetry_service.py`.
- Create `backend/tests/telemetry/test_quality_metrics.py`.
- Create `backend/tests/regression/test_regression_service.py`.
- Create `backend/tests/api/test_quality_api.py`.
- Create `backend/tests/api/test_regression_api.py`.
- Create `backend/tests/api/test_system_api.py`.
- Modify `backend/tests/api/test_dashboard_static.py`.
- Create `backend/tests/e2e/test_quality_regression_flow.py`.
- Create `scripts/validate_observability_ui.mjs` and modify `scripts/validate_local.sh`.
- Modify `README.md` and `.superpowers/sdd/2026-10-21-feedback-runtime-observability/progress.md`.

---

### Task 1: Persisted Run and Regression Records

**Files:**
- Create: `backend/app/persistence/migrations/004_agent_quality_regression.sql`
- Modify: `backend/app/persistence/models.py`
- Modify: `backend/app/persistence/sqlite.py`
- Test: `backend/tests/persistence/test_quality_regression_repositories.py`

**Interfaces:**
- Consumes: existing `SqliteUnitOfWork`, migration runner, ISO UTC datetime encoding, repository transaction pattern.
- Produces: `AgentRunRepository`, `AgentRunStepRepository`, `RegressionCaseRepository`, and `RegressionCaseRunRepository` available as unit-of-work properties.

- [ ] **Step 1: Write failing migration and repository tests**

Add tests named `test_migration_004_creates_quality_regression_schema`, `test_agent_run_repository_completes_run_atomically`, `test_run_steps_allocate_monotonic_sequence`, and `test_regression_case_origin_and_runs_round_trip`. Assert foreign keys, required CHECK constraints, `NULL` cost preservation, and cascade behavior.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `PYTHONPATH=backend:benchmarks/src benchmarks/.venv/bin/pytest -q backend/tests/persistence/test_quality_regression_repositories.py`

Expected: FAIL because migration 004 and repository properties do not exist.

- [ ] **Step 3: Implement migration 004 and persistence models**

Create tables `agent_runs`, `agent_run_steps`, `regression_cases`, and `regression_case_runs` with the exact enums and relationships in the spec. Rebuild `runtime_issues` transactionally so its status CHECK also accepts `resolved_verified` while preserving all rows and indexes. Add Pydantic records `AgentRunRecord`, `AgentRunStepRecord`, `RegressionCaseRecord`, and `RegressionCaseRunRecord`.

- [ ] **Step 4: Implement focused repositories**

Add repository methods for create/get/list/update lifecycle operations, atomic step-sequence allocation, source lookup, batch listing, and latest case result. Use parameterized SQL and the existing unit-of-work transaction boundary.

- [ ] **Step 5: Run persistence tests and migration compatibility tests**

Run: `PYTHONPATH=backend:benchmarks/src benchmarks/.venv/bin/pytest -q backend/tests/persistence backend/tests/api/test_persistent_app_restart.py`

Expected: PASS.

- [ ] **Step 6: Record checkpoint**

Update the SDD progress ledger with migration number, table names, test command, and result.

### Task 2: Unified Runtime Telemetry

**Files:**
- Create: `backend/app/telemetry/__init__.py`
- Create: `backend/app/telemetry/models.py`
- Create: `backend/app/telemetry/service.py`
- Modify: `backend/app/agent/session_service.py`
- Modify: `backend/app/agent/runtime.py`
- Modify: `backend/app/evaluation/runtime_task_runner.py`
- Test: `backend/tests/telemetry/test_telemetry_service.py`
- Modify: `backend/tests/agent/test_session_service.py`
- Modify: `backend/tests/evaluation/test_runtime_task_runner.py`

**Interfaces:**
- Consumes: Task 1 repositories; existing runtime events, planner usage, stop reasons, and outcome checks.
- Produces: `RunTelemetryService.start_run(command) -> AgentRunRecord`, `record_step(run_id, command) -> AgentRunStepRecord`, `finish_run(run_id, command) -> AgentRunRecord`, and `recover_stale_runs(cutoff) -> int`.

- [ ] **Step 1: Write failing telemetry lifecycle tests**

Test successful, failed, waiting-confirmation, and unsupported-price runs. Add `test_recover_stale_running_rows_marks_them_failed`, `test_parallel_step_writes_keep_unique_sequence`, and `test_telemetry_failure_does_not_replace_agent_result`.

- [ ] **Step 2: Run telemetry tests and verify RED**

Run: `PYTHONPATH=backend:benchmarks/src benchmarks/.venv/bin/pytest -q backend/tests/telemetry/test_telemetry_service.py`

Expected: FAIL because `RunTelemetryService` is missing.

- [ ] **Step 3: Implement telemetry commands and service**

Define `StartRunCommand`, `RecordStepCommand`, and `FinishRunCommand`. Centralize UTC timing, duration calculation, sanitized step summaries, status mapping, Token/cost preservation, and runtime-issue linkage in `RunTelemetryService`.

- [ ] **Step 4: Instrument support and sandbox runs**

Inject an optional telemetry service into `AgentSessionService`; start on user-triggered auto-run, record planner/guard/tool/confirmation/response steps from existing events, and finish in a `finally`-safe lifecycle. Preserve all existing return types and behavior when telemetry is absent.

- [ ] **Step 5: Instrument benchmark and regression runs**

Have `run_retail_task_subset` accept an optional telemetry service and source, then finish records with business, gate, confirmed-state, exact-match, Token, cost, and stop-reason fields.

- [ ] **Step 6: Run Agent and evaluation tests**

Run: `PYTHONPATH=backend:benchmarks/src benchmarks/.venv/bin/pytest -q backend/tests/telemetry backend/tests/agent backend/tests/evaluation/test_runtime_task_runner.py`

Expected: PASS with no behavior regressions.

- [ ] **Step 7: Record checkpoint**

Document run status mapping, stale timeout, and focused test results in the progress ledger.

### Task 3: Quality Aggregation and Run APIs

**Files:**
- Create: `backend/app/telemetry/quality.py`
- Create: `backend/app/api/quality.py`
- Modify: `backend/app/api/main.py`
- Test: `backend/tests/telemetry/test_quality_metrics.py`
- Test: `backend/tests/api/test_quality_api.py`

**Interfaces:**
- Consumes: completed and active run records from Tasks 1-2, feedback and issue repositories, authenticated developer actor.
- Produces: `QualityService.overview(filters)`, `trends(filters)`, `tools(filters)`, `list_runs(filters)`, and `get_run(run_id)` plus `/api/v1/quality/*` and `/api/v1/runs/*` routes.

- [ ] **Step 1: Write failing pure metric tests**

Cover empty windows, singleton percentiles, mixed run states, waiting confirmation, mixed Token/price availability, source/model filters, daily buckets, tool success/failure ranking, and the exact formulas in the spec.

- [ ] **Step 2: Run metric tests and verify RED**

Run: `PYTHONPATH=backend:benchmarks/src benchmarks/.venv/bin/pytest -q backend/tests/telemetry/test_quality_metrics.py`

Expected: FAIL because quality aggregation is missing.

- [ ] **Step 3: Implement pure aggregation functions**

Implement `nearest_rank_percentile(values: list[int], percentile: float) -> int | None` and focused aggregators that return typed overview, trend, and tool metric models without querying global state.

- [ ] **Step 4: Write failing API authorization and filtering tests**

Assert developer success, customer 403, time range validation, pagination, missing run 404, no leaked context, and stable empty responses.

- [ ] **Step 5: Implement quality service and router**

Add developer-only endpoints from the spec and wire them through `create_app`. Use repository filters rather than loading unbounded tables.

- [ ] **Step 6: Run quality and authorization tests**

Run: `PYTHONPATH=backend:benchmarks/src benchmarks/.venv/bin/pytest -q backend/tests/telemetry/test_quality_metrics.py backend/tests/api/test_quality_api.py backend/tests/api/test_auth_api.py`

Expected: PASS.

- [ ] **Step 7: Record checkpoint**

Add metric definitions and API verification results to the progress ledger.

### Task 4: Regression Case Library and Batch Runner

**Files:**
- Create: `backend/app/regression/__init__.py`
- Create: `backend/app/regression/models.py`
- Create: `backend/app/regression/service.py`
- Create: `backend/app/api/regression.py`
- Modify: `backend/app/api/main.py`
- Modify: `backend/app/evaluation/runtime_task_runner.py`
- Test: `backend/tests/regression/test_regression_service.py`
- Test: `backend/tests/api/test_regression_api.py`

**Interfaces:**
- Consumes: Task 1 case repositories, Task 2 telemetry service, tau2 task loader, runtime subset runner, authenticated developer.
- Produces: draft/active/retired case lifecycle; `RegressionService.run_batch(command) -> RegressionBatch`; case and batch APIs in the spec.

- [ ] **Step 1: Write failing case validation tests**

Cover valid tau2 cases, valid conversation replay cases, missing expectations, unsafe fixture fields, duplicate origins, retired cases, and deterministic pass/fail/blocked classification.

- [ ] **Step 2: Run service tests and verify RED**

Run: `PYTHONPATH=backend:benchmarks/src benchmarks/.venv/bin/pytest -q backend/tests/regression/test_regression_service.py`

Expected: FAIL because regression domain models and service are missing.

- [ ] **Step 3: Implement case lifecycle and validators**

Define typed `RegressionExpectation`, `RegressionFixture`, `RegressionCase`, `RegressionBatchCommand`, and result models. Drafts may be incomplete; activation requires replayable fixture data and at least one explicit expected business, tool, confirmation, or persistence condition.

- [ ] **Step 4: Implement batch execution**

Execute tau2 cases through `run_retail_task_subset`; execute conversation fixtures through the normal session service in an isolated runtime. Persist each case run and Agent run, classify environment failures as `blocked`, and never mutate the source fixture.

- [ ] **Step 5: Write failing API tests**

Cover list/create/update, activate/retire, single and multi-case batches, unknown IDs, customer 403, and batch result retrieval.

- [ ] **Step 6: Implement regression router and wiring**

Expose the case and batch endpoints from the spec with stable error payloads and developer authorization.

- [ ] **Step 7: Run regression tests**

Run: `PYTHONPATH=backend:benchmarks/src benchmarks/.venv/bin/pytest -q backend/tests/regression backend/tests/api/test_regression_api.py backend/tests/evaluation/test_runtime_task_runner.py`

Expected: PASS.

- [ ] **Step 8: Record checkpoint**

Document case status rules, blocked classification, and focused test results.

### Task 5: Issue and Feedback Conversion Loop

**Files:**
- Modify: `backend/app/observability/models.py`
- Modify: `backend/app/observability/service.py`
- Modify: `backend/app/api/observability.py`
- Modify: `backend/app/api/regression.py`
- Modify: `backend/app/persistence/sqlite.py`
- Test: `backend/tests/regression/test_regression_service.py`
- Modify: `backend/tests/api/test_support_feedback_api.py`
- Modify: `backend/tests/api/test_observability_api.py`
- Modify: `backend/tests/api/test_regression_api.py`

**Interfaces:**
- Consumes: Task 4 draft creation and latest-case-result lookup.
- Produces: conversions from issue, feedback, and run; source details with linked cases; verified-resolution guard.

- [ ] **Step 1: Write failing conversion tests**

Assert that a replayable source creates one draft with sanitized fixture data, repeated conversion returns the existing draft, insufficient source data still creates only an incomplete draft, and secrets never appear in fixture JSON.

- [ ] **Step 2: Write failing verified-resolution tests**

Assert an issue cannot enter `resolved_verified` without a latest passing linked case; ignored issues remain allowed; a later failed run removes verification eligibility without rewriting historical status.

- [ ] **Step 3: Run observability/regression tests and verify RED**

Run: `PYTHONPATH=backend:benchmarks/src benchmarks/.venv/bin/pytest -q backend/tests/regression/test_regression_service.py backend/tests/api/test_observability_api.py backend/tests/api/test_regression_api.py`

Expected: FAIL on missing conversion and verification behavior.

- [ ] **Step 4: Implement source conversion and links**

Reuse the existing redaction service, store origin type/id on the case, expose linked case summaries from issue/feedback/run details, and keep source records immutable apart from review metadata.

- [ ] **Step 5: Implement verified-resolution transition**

Extend issue review status with `resolved_verified`, enforce the passing-case precondition in the service, and return a structured 409 when it is not met.

- [ ] **Step 6: Run focused tests**

Run: `PYTHONPATH=backend:benchmarks/src benchmarks/.venv/bin/pytest -q backend/tests/regression backend/tests/api/test_observability_api.py backend/tests/api/test_support_feedback_api.py backend/tests/api/test_regression_api.py`

Expected: PASS.

- [ ] **Step 7: Record checkpoint**

Record the conversion eligibility and verified-resolution rules.

### Task 6: Consolidated System Status

**Files:**
- Create: `backend/app/api/system.py`
- Modify: `backend/app/api/main.py`
- Modify: `backend/app/agent/proposal_generator.py`
- Test: `backend/tests/api/test_system_api.py`

**Interfaces:**
- Consumes: existing `/health`, config loader, tool backend metadata, tau2 Retail loaders, SQLite migration status, and authenticated developer.
- Produces: `GET /api/v1/system/status` with service, MCP, SQLite, Planner/model, policy, data source/version, counts, and active alert summary.

- [ ] **Step 1: Write failing system status tests**

Cover healthy dependencies, MCP unavailable, missing pricing, policy unavailable, developer-only access, and ensure secrets and full policy text are absent.

- [ ] **Step 2: Run tests and verify RED**

Run: `PYTHONPATH=backend:benchmarks/src benchmarks/.venv/bin/pytest -q backend/tests/api/test_system_api.py`

Expected: FAIL because the consolidated endpoint is missing.

- [ ] **Step 3: Implement system status service/router**

Return compact typed component statuses, default Planner and model, LLM limits, MCP metadata, policy loaded/version state, tau2 source/counts, SQLite migration version, and critical-alert count. Use bounded dependency probes.

- [ ] **Step 4: Run API tests**

Run: `PYTHONPATH=backend:benchmarks/src benchmarks/.venv/bin/pytest -q backend/tests/api/test_system_api.py backend/tests/api/test_app_config.py backend/tests/mcp`

Expected: PASS.

- [ ] **Step 5: Record checkpoint**

Record the status payload contract and dependency timeout behavior.

### Task 7: Six-Module Dashboard

**Files:**
- Modify: `backend/app/static/dashboard/index.html`
- Modify: `backend/app/static/dashboard/styles.css`
- Modify: `backend/app/static/dashboard/app.js`
- Create: `backend/app/static/dashboard/api.js`
- Create: `backend/app/static/dashboard/quality.js`
- Create: `backend/app/static/dashboard/runs.js`
- Create: `backend/app/static/dashboard/regression.js`
- Create: `backend/app/static/dashboard/operations.js`
- Create: `backend/app/static/dashboard/system.js`
- Modify: `backend/tests/api/test_dashboard_static.py`
- Create: `scripts/validate_observability_ui.mjs`

**Interfaces:**
- Consumes: Tasks 3-6 developer APIs and existing auth/developer-management APIs.
- Produces: six routes `overview`, `runs`, `regression`, `issues`, `feedback`, and `system`, with accessible tabs inside regression and system modules.

- [ ] **Step 1: Write failing static UI contract tests**

Assert exactly six primary navigation entries; required quality metric IDs; run detail and conversion actions; regression tabs; compact top health; and absence of old primary routes, generic tool runner, cancel demo, and task 0/1/2 demo controls.

- [ ] **Step 2: Run static tests and verify RED**

Run: `PYTHONPATH=backend:benchmarks/src benchmarks/.venv/bin/pytest -q backend/tests/api/test_dashboard_static.py`

Expected: FAIL against the current ten-entry Dashboard.

- [ ] **Step 3: Replace Dashboard information architecture**

Rewrite `index.html` around the six modules. Keep page sections unframed with panels only for real metrics, repeated records, filters, and detail tools. Use existing restrained visual language, 8px-or-less radii, stable responsive grids, and Chinese interface copy.

- [ ] **Step 4: Extract API and module controllers**

Change the Dashboard script to `type="module"`. Put auth/error handling in `api.js`; render quality, runs, regression, operations, and system screens in their named modules. Keep `app.js` responsible for navigation, refresh coordination, identity, and logout.

- [ ] **Step 5: Implement quality and run views**

Render time filters, KPI summaries, accessible CSS trend charts, tool rankings, recent failures, run filtering, run steps, and audit evidence. Unknown costs render `N/A` with an explanatory label, not zero.

- [ ] **Step 6: Implement regression and operations views**

Render execution, case library, history, and sandbox tabs; add source-to-case actions and linked verification status to issue/feedback details. Preserve explicit Planner/model labels for each run.

- [ ] **Step 7: Implement system view and compact global health**

Move environment configuration and developer management into System. Topbar shows only API/MCP/critical-alert health and links to system detail.

- [ ] **Step 8: Run static and browser UI validation**

Run: `PYTHONPATH=backend:benchmarks/src benchmarks/.venv/bin/pytest -q backend/tests/api/test_dashboard_static.py`

Then, with the product stack running: `node scripts/validate_observability_ui.mjs`

Expected: desktop and mobile checks pass; no overflow, overlapping controls, missing modules, console errors, or failed API requests.

- [ ] **Step 9: Record checkpoint**

Record removed routes/controls, screenshots checked, viewports, and UI validation output.

### Task 8: End-to-End Closure, Documentation, and Full Verification

**Files:**
- Create: `backend/tests/e2e/test_quality_regression_flow.py`
- Modify: `scripts/validate_local.sh`
- Modify: `README.md`
- Modify: `.env.example`
- Modify: `.superpowers/sdd/2026-10-21-feedback-runtime-observability/progress.md`

**Interfaces:**
- Consumes: all prior tasks.
- Produces: one verified workflow from support run through issue/case creation and passing replay, plus current setup and operation documentation.

- [ ] **Step 1: Write the failing end-to-end workflow test**

Create a customer conversation, execute a run, capture a deterministic failure, verify quality metrics, convert the issue to a draft case, add expectations, activate it, replay it after the controlled failure is removed, and assert the issue can become verified resolved.

- [ ] **Step 2: Run the E2E test and verify RED**

Run: `PYTHONPATH=backend:benchmarks/src benchmarks/.venv/bin/pytest -q backend/tests/e2e/test_quality_regression_flow.py`

Expected: FAIL until every integration path is wired.

- [ ] **Step 3: Repair integration gaps only**

Fix dependency wiring, transaction ownership, serialization, or status transitions exposed by the E2E test. Do not add unrelated features.

- [ ] **Step 4: Update setup and operator documentation**

Document the six modules, metric definitions, telemetry start date, data provenance, issue-to-test workflow, model quota errors, and local startup/shutdown. Add only environment variables actually introduced by implementation.

- [ ] **Step 5: Run the complete backend suite**

Run: `PYTHONPATH=backend:benchmarks/src benchmarks/.venv/bin/pytest -q backend/tests`

Expected: all tests pass; only the existing Python `audioop` deprecation warning may remain.

- [ ] **Step 6: Run local validation gates**

Run: `./scripts/validate_local.sh`

With the complete stack running, run: `node scripts/validate_support_ui.mjs` and `node scripts/validate_observability_ui.mjs`.

Expected: all offline gates, support UI, six-module Dashboard desktop/mobile checks, API/MCP health, and regression workflow pass.

- [ ] **Step 7: Perform final requirement audit**

Check every acceptance criterion in the spec against a test or fresh manual observation. Record any production-only residual work explicitly rather than marking it complete.

- [ ] **Step 8: Final progress ledger entry**

Record migrations, final test count, UI viewports, live MCP checks, real LLM checks performed or intentionally skipped, and remaining external deployment risks.

