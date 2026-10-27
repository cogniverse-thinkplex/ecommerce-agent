# Standalone Customer Support Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a persistent Chinese customer-support web application at `/support/`, backed by the existing guarded agent runtime and a selectable real MCP retail-tool service.

**Architecture:** Add repository protocols and a standard-library SQLite implementation beneath a support application service, while leaving benchmark construction explicitly in-memory. Expose versioned support APIs and a modular static frontend; implement MCP Streamable HTTP as another `RetailToolPort` backend and package the API plus MCP server for Conda and Docker Compose operation.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, stdlib `sqlite3`, MCP Python SDK, tau2 retail environment, vanilla HTML/CSS/JavaScript, pytest, FastAPI TestClient, Playwright/browser automation, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-10-20-standalone-customer-support-center-design.md`

## Global Constraints

- `/support/` is customer-facing; `/dashboard/` remains internal and existing evaluation behavior must remain compatible.
- Business results must come from `RetailToolPort`; the support frontend may not manufacture order, product, profile, or mutation results.
- Every write requires a persisted explicit confirmation and revalidation through `GuardedRetailToolExecutor`.
- Default local persistence is SQLite at `./data/ecommerce_agent.db`, with WAL mode, foreign keys, transactions, and versioned migrations.
- Default quasi-product tool backend is MCP; `tau2_python` remains an explicit benchmark/fallback choice and no write silently falls back.
- The customer UI and APIs must not expose policy text, prompts, tool names, raw arguments, reward, cost, or raw traces.
- Customer-facing copy is Chinese; benchmark source data may remain English.
- The current directory has no `.git`; each task ends with an independently passing test gate and a plan checkpoint instead of an unavailable Git commit.

## Review Focus

- Duplicate message or confirmation requests must not create duplicate turns or execute a write twice; Task 3 and Task 4 add request-ID and compare-and-set tests.
- Empty, whitespace-only, oversized, or malformed support input must produce stable 4xx responses without corrupting state; Task 4 adds boundary tests.
- A conversation already authenticated as one user must reject attempts to switch identity or access another user; Task 3 adds scope tests.
- API restart during a pending or executing action must preserve a recoverable state and must not auto-replay the write; Task 2 and Task 8 add restart tests.
- MCP timeout, malformed content, missing tools, and transport loss must produce classified recoverable errors without direct-backend fallback; Task 6 adds contract tests.

---

### Task 1: SQLite Persistence Foundation

**Files:**
- Create: `backend/app/persistence/__init__.py`
- Create: `backend/app/persistence/models.py`
- Create: `backend/app/persistence/repositories.py`
- Create: `backend/app/persistence/sqlite.py`
- Create: `backend/app/persistence/migrations/001_initial.sql`
- Test: `backend/tests/persistence/test_sqlite_repositories.py`

**Interfaces:**
- Consumes: `CustomerAgentState.model_dump_json()` and `CustomerAgentState.model_validate_json()`.
- Produces: `ConversationRecord`, `MessageRecord`, `PendingActionRecord`, `AuditEventRecord`; repository protocols; `SqliteUnitOfWork(path: Path)` with `initialize()`, `transaction()`, and repository properties.

- [ ] **Step 1: Write failing migration and repository tests**

  Cover idempotent initialization, foreign keys, WAL mode, conversation round-trip, ordered messages, pending-action status compare-and-set, unique request/idempotency keys, archive-not-delete behavior, and transaction rollback.

- [ ] **Step 2: Run the focused tests and verify missing-module failures**

  Run: `scripts/test_backend.sh backend/tests/persistence/test_sqlite_repositories.py -v`
  Expected: FAIL because `app.persistence` does not exist.

- [ ] **Step 3: Define persistence records and protocols**

  Use Pydantic models with UTC ISO timestamps and `Literal` statuses. Define repository methods with exact conversation/action identifiers; do not expose SQL outside `sqlite.py`.

- [ ] **Step 4: Implement migration runner and SQLite repositories**

  Use `sqlite3`, `PRAGMA foreign_keys=ON`, `PRAGMA journal_mode=WAL`, parameterized statements, explicit commit/rollback, migration version `1`, and compare-and-set SQL for action transitions.

- [ ] **Step 5: Run persistence tests**

  Run: `scripts/test_backend.sh backend/tests/persistence/test_sqlite_repositories.py -v`
  Expected: all tests PASS.

- [ ] **Step 6: Record Task 1 checkpoint in this plan**

  Mark the task complete only after the focused suite passes; do not modify agent runtime behavior in this task.

### Task 2: Persistent Agent Session Store

**Files:**
- Create: `backend/app/agent/session_store.py`
- Modify: `backend/app/agent/session_service.py`
- Modify: `backend/app/api/main.py`
- Test: `backend/tests/agent/test_persistent_session_service.py`
- Test: `backend/tests/api/test_persistent_app_restart.py`

**Interfaces:**
- Consumes: `ConversationRepository.get_state(conversation_id)` and `save_state(state)` from Task 1.
- Produces: `SessionStore` protocol; `InMemorySessionStore`; `PersistentSessionStore`; `AgentSessionService(..., session_store: SessionStore | None = None)`.

- [ ] **Step 1: Write failing store compatibility tests**

  Assert existing in-memory semantics remain unchanged, persistent service lazily reloads a state, all mutating service methods save the resulting state, archived sessions are absent, and a pending confirmation survives service reconstruction.

- [ ] **Step 2: Run focused tests and verify interface failures**

  Run: `scripts/test_backend.sh backend/tests/agent/test_persistent_session_service.py backend/tests/api/test_persistent_app_restart.py -v`
  Expected: FAIL because `SessionStore` and persistent dependency construction are absent.

- [ ] **Step 3: Add the session-store abstraction**

  Define `create(state)`, `get(conversation_id)`, `save(state)`, `list()`, and `archive(conversation_id)`. Make the default `InMemorySessionStore` preserve every existing test contract.

- [ ] **Step 4: Refactor `AgentSessionService` to use `SessionStore`**

  Replace direct `_sessions` access without changing public return types. Save only completed state transitions; never persist a partially applied node result.

- [ ] **Step 5: Add SQLite dependency construction**

  Add `ECOM_AGENT_STORE` and `ECOM_AGENT_SQLITE_PATH` handling. Keep evaluation helpers explicitly in-memory. Initialize schema once at application startup.

- [ ] **Step 6: Run focused and existing session tests**

  Run: `scripts/test_backend.sh backend/tests/agent/test_session_service.py backend/tests/agent/test_persistent_session_service.py backend/tests/api/test_sessions_api.py backend/tests/api/test_persistent_app_restart.py -v`
  Expected: all tests PASS.

### Task 3: Support Application Service and User-Safe Projections

**Files:**
- Create: `backend/app/support/__init__.py`
- Create: `backend/app/support/models.py`
- Create: `backend/app/support/projector.py`
- Create: `backend/app/support/service.py`
- Test: `backend/tests/support/test_projector.py`
- Test: `backend/tests/support/test_support_service.py`

**Interfaces:**
- Consumes: `AgentSessionService.auto_run()`, `confirm_pending_and_continue()`, persistence repositories, and `build_session_audit()`.
- Produces: `SupportService.create_conversation()`, `list_conversations()`, `get_conversation()`, `submit_message()`, `confirm_action()`, `reject_action()`, `retry_latest()`; `SupportMessageBlock` discriminated union and user-safe response models.

- [ ] **Step 1: Write failing projection tests**

  Assert text, authentication request, order/product/profile summaries, confirmation, operation result, transfer state, and recoverable-error blocks contain only allowlisted fields. Assert policy, tool names, raw arguments, cost, reward, and traces never appear.

- [ ] **Step 2: Write failing service-flow tests**

  Cover conversation creation, one-user authentication scope, query projection, pending-write persistence, reject-without-execution, confirmed execution, audit persistence, duplicate request ID, duplicate confirmation, and identity-switch denial.

- [ ] **Step 3: Run support tests and verify missing-module failures**

  Run: `scripts/test_backend.sh backend/tests/support -v`
  Expected: FAIL because `app.support` does not exist.

- [ ] **Step 4: Implement support models and projector**

  Use stable block types from the spec. Parse trusted structured tool content; when content cannot be safely projected, emit Chinese text or a recoverable error rather than raw payloads.

- [ ] **Step 5: Implement `SupportService` transaction boundaries**

  Persist request IDs before runtime execution, create pending actions atomically with confirmation messages, and use compare-and-set before confirmation execution. Reject action IDs not belonging to the conversation.

- [ ] **Step 6: Run support tests**

  Run: `scripts/test_backend.sh backend/tests/support -v`
  Expected: all tests PASS.

### Task 4: Versioned Support API

**Files:**
- Create: `backend/app/api/support.py`
- Modify: `backend/app/api/main.py`
- Test: `backend/tests/api/test_support_api.py`
- Test: `backend/tests/api/test_support_api_errors.py`

**Interfaces:**
- Consumes: Task 3 `SupportService` methods and response models.
- Produces: `/api/v1/support` routes and dependency override `get_support_service()`; enhanced `/health` component status.

- [ ] **Step 1: Write failing route and boundary tests**

  Cover all endpoints from the spec, message pagination, request IDs, 404 ownership isolation, whitespace-only and oversized messages, malformed UUIDs, duplicate confirmation, safe 409 state conflicts, and redacted 500 responses.

- [ ] **Step 2: Run API tests and verify 404/missing-router failures**

  Run: `scripts/test_backend.sh backend/tests/api/test_support_api.py backend/tests/api/test_support_api_errors.py -v`
  Expected: FAIL because support routes are not mounted.

- [ ] **Step 3: Implement the support router**

  Use a FastAPI `APIRouter(prefix="/api/v1/support")`. Limit message content to 8,000 characters, pagination limit to 100, and return stable error objects with `code`, `message`, and `recoverable`.

- [ ] **Step 4: Add application wiring and health details**

  Construct one support service per application, mount the router, and report `database`, `model`, and `tool_backend` statuses without secrets or policy content.

- [ ] **Step 5: Run API and legacy API tests**

  Run: `scripts/test_backend.sh backend/tests/api -v`
  Expected: all tests PASS.

### Task 5: Complete Customer Support Web Application

**Files:**
- Create: `backend/app/static/support/index.html`
- Create: `backend/app/static/support/styles.css`
- Create: `backend/app/static/support/app.js`
- Create: `backend/app/static/support/api.js`
- Create: `backend/app/static/support/session.js`
- Create: `backend/app/static/support/chat.js`
- Create: `backend/app/static/support/cards.js`
- Create: `backend/app/static/support/history.js`
- Modify: `backend/app/api/main.py`
- Test: `backend/tests/api/test_support_static.py`

**Interfaces:**
- Consumes: Task 4 JSON endpoints and structured message block schemas.
- Produces: `/support/` static application with history, chat, authentication, business cards, confirmation controls, operation state, retry, and mobile drawer.

- [ ] **Step 1: Write failing static-contract tests**

  Assert `/support/` loads, module files are served, the HTML is Chinese and semantic, form controls have accessible names, CSP-safe local assets are used, and no internal dashboard vocabulary appears.

- [ ] **Step 2: Run static tests and verify missing mount failure**

  Run: `scripts/test_backend.sh backend/tests/api/test_support_static.py -v`
  Expected: FAIL with `/support/` not found.

- [ ] **Step 3: Build the semantic application shell and visual system**

  Implement a restrained customer-service layout with a session rail, responsive drawer, header status, message stream, sticky composer, focused business cards, loading/empty/error states, visible focus, and reduced motion. Avoid nested cards and decorative gradients.

- [ ] **Step 4: Implement API and session modules**

  Generate request UUIDs, normalize API errors, store only the selected conversation ID in local storage, fetch authoritative history from the API, and prevent duplicate submissions while a request is active.

- [ ] **Step 5: Implement chat, history, and structured cards**

  Render text safely with DOM text nodes, render only known block types, disable confirmation controls immediately after selection, announce updates through an ARIA live region, and restore focus after actions.

- [ ] **Step 6: Mount `/support/` and redirect `/` to it**

  Keep `/dashboard/` unchanged and directly addressable.

- [ ] **Step 7: Run static and API tests**

  Run: `scripts/test_backend.sh backend/tests/api/test_support_static.py backend/tests/api/test_support_api.py -v`
  Expected: all tests PASS.

### Task 6: MCP Retail Server and Adapter

**Files:**
- Modify: `benchmarks/pyproject.toml`
- Create: `backend/app/mcp/__init__.py`
- Create: `backend/app/mcp/retail_server.py`
- Create: `backend/app/tools/mcp_retail_adapter.py`
- Modify: `backend/app/tools/tool_backend_factory.py`
- Create: `scripts/run_retail_mcp.sh`
- Test: `backend/tests/mcp/test_retail_server.py`
- Test: `backend/tests/tools/test_mcp_retail_adapter.py`
- Modify: `backend/tests/tools/test_tool_backend_factory.py`

**Interfaces:**
- Consumes: `TauRetailAdapter`, MCP Python SDK Streamable HTTP client/server APIs, and `RetailToolPort` dataclasses.
- Produces: `McpRetailAdapter(base_url: str, timeout_seconds: float)`; MCP server entrypoint; `ECOM_AGENT_MCP_URL` and `ECOM_AGENT_MCP_TIMEOUT_SECONDS` settings.

- [ ] **Step 1: Add a bounded MCP SDK dependency**

  Add `mcp>=1.20,<2` to project dependencies and sync the existing environment. Do not change unrelated tau2 dependencies.

- [ ] **Step 2: Write failing MCP server and adapter tests**

  Assert the 16-tool catalogue matches the direct adapter, policy retrieval is available as server metadata/resource rather than a customer tool, read and write results normalize exactly, and `managed_by_mcp=True`.

- [ ] **Step 3: Add failure contract tests**

  Cover startup with missing tools, timeout, connection loss, malformed structured content, unknown tool, and no silent call to `TauRetailAdapter` inside the client process.

- [ ] **Step 4: Run MCP tests and verify missing implementation failures**

  Run: `scripts/test_backend.sh backend/tests/mcp backend/tests/tools/test_mcp_retail_adapter.py backend/tests/tools/test_tool_backend_factory.py -v`
  Expected: FAIL because the MCP server and adapter do not exist.

- [ ] **Step 5: Implement the MCP server**

  Create one tau2 retail environment per server process, expose every retail operation with its declared JSON schema, preserve structured/error responses, and serve Streamable HTTP on configurable host/port.

- [ ] **Step 6: Implement `McpRetailAdapter`**

  Validate required catalogue entries on initialization, map sync `RetailToolPort` calls through a safely managed async MCP session, preserve call IDs, classify transport/protocol/tool errors, and expose `db_hash` evidence through a private MCP capability used by the guarded executor.

- [ ] **Step 7: Wire explicit backend selection**

  Replace the current MCP-not-implemented error in `build_retail_tool_port()` with adapter construction. Never catch MCP construction/call errors and return a direct adapter.

- [ ] **Step 8: Run MCP and guard parity tests**

  Run: `scripts/test_backend.sh backend/tests/mcp backend/tests/tools -v`
  Expected: all tests PASS.

### Task 7: Local Startup and Docker Compose Packaging

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.dockerignore`
- Create: `scripts/run_local_product.sh`
- Modify: `.env.example`
- Modify: `scripts/run_backend_api.sh`
- Test: `backend/tests/ops/test_runtime_configuration.py`
- Test: `scripts/validate_product_stack.sh`

**Interfaces:**
- Consumes: Task 2 database configuration and Task 6 MCP configuration.
- Produces: one-command Conda/local startup; `api` and `retail-mcp` Compose services; persisted `agent-data` volume; component health checks.

- [ ] **Step 1: Write failing configuration tests**

  Assert documented defaults, writable data-directory creation, invalid backend/store rejection, secret-free `.env.example`, MCP URL use in Compose, and loopback defaults outside containers.

- [ ] **Step 2: Run configuration tests and verify missing artifacts**

  Run: `scripts/test_backend.sh backend/tests/ops/test_runtime_configuration.py -v`
  Expected: FAIL because product configuration and packaging are absent.

- [ ] **Step 3: Implement local process startup**

  Start MCP first, wait for readiness, then start FastAPI; forward signals and stop both processes on exit. Preserve user environment settings and print `/support/` and `/dashboard/` URLs.

- [ ] **Step 4: Implement container packaging**

  Use one image with separate commands, non-root runtime user, API port 8000, internal MCP port, named SQLite volume, health checks, and `depends_on` readiness.

- [ ] **Step 5: Add stack validation script**

  Verify health, load `/support/`, create a conversation, and confirm the configured backend reports MCP. Fail on any non-2xx response or backend mismatch.

- [ ] **Step 6: Run configuration tests and validate Compose syntax**

  Run: `scripts/test_backend.sh backend/tests/ops/test_runtime_configuration.py -v`
  Run: `docker compose config --quiet`
  Expected: tests PASS and Compose exits 0. If Docker is unavailable, record that limitation and still run local-stack validation.

### Task 8: End-to-End Recovery, Browser, and Full Regression Validation

**Files:**
- Create: `backend/tests/e2e/test_support_product_flow.py`
- Create: `backend/tests/e2e/test_support_restart_recovery.py`
- Create: `scripts/validate_support_ui.mjs`
- Modify: `scripts/validate_local.sh`
- Modify: `README.md`
- Modify: `docs/final_implementation_roadmap.md`

**Interfaces:**
- Consumes: complete support API/UI, persistent store, MCP service, local startup, existing validation suite.
- Produces: repeatable acceptance test suite, desktop/mobile screenshots, updated operation guide, and documented remaining production gap.

- [ ] **Step 1: Write failing end-to-end API scenarios**

  Cover authentication plus order query, confirmed cancellation with changed-state evidence, rejected mutation with unchanged state, cross-user denial, browser/API restart persistence, interrupted `executing` action recovery, and MCP outage without false success.

- [ ] **Step 2: Run E2E tests and verify uncovered failures**

  Run: `scripts/test_backend.sh backend/tests/e2e -v`
  Expected: FAIL until all lifecycle and recovery behavior is wired end to end.

- [ ] **Step 3: Repair only integration gaps exposed by E2E tests**

  Keep fixes in the owning modules from Tasks 1-7; do not introduce demonstration-only data paths or bypass the guard.

- [ ] **Step 4: Add browser validation**

  Automate desktop `1440x900` and mobile `390x844` flows. Assert no horizontal overflow, visible composer, usable history drawer, keyboard focus, confirmation disabled-after-click, persisted reload, and absence of internal policy/trace/cost text. Save screenshots under `docs/validation/support/`.

- [ ] **Step 5: Update README and roadmap**

  Document prerequisites, environment variables, Conda startup, Docker Compose startup, `/support/` user workflow, `/dashboard/` engineering role, MCP diagnostics, database location/reset, tests, and the explicitly deferred final 10%.

- [ ] **Step 6: Run focused E2E and browser validation**

  Run: `scripts/test_backend.sh backend/tests/e2e -v`
  Run: `node scripts/validate_support_ui.mjs`
  Expected: all flows PASS and both viewport screenshots contain a usable nonblank application.

- [ ] **Step 7: Run the complete regression suite**

  Run: `scripts/test_backend.sh -q`
  Run: `scripts/validate_local.sh`
  Expected: all backend tests and every saved-artifact quality gate PASS.

- [ ] **Step 8: Perform final acceptance review against the design spec**

  Confirm every acceptance criterion in Section 14 of the spec has direct test or browser evidence. Record any environment-only limitation instead of declaring it complete.
