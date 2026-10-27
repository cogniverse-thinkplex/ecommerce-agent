# Streaming Support, Permissions, and Human Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make customer conversations stream real operational progress and incremental result blocks while enforcing explicit one-operation write confirmation and providing a durable developer-operated human handoff queue.

**Architecture:** Preserve the synchronous Agent and JSON API, then add an optional progress callback and a queue-backed SSE adapter around it. Reuse existing confirmation fingerprints and pending actions for write authorization, and add a focused SQLite-backed handoff service shared by customer and developer APIs.

**Tech Stack:** Python 3.12, FastAPI/Starlette `StreamingResponse`, Pydantic, SQLite migrations/repositories, vanilla ES modules and Fetch readable streams, pytest, Node browser acceptance scripts.

**Spec:** `docs/superpowers/specs/2026-10-22-streaming-permissions-human-handoff-design.md`

## Global Constraints

- Never expose chain-of-thought, raw prompts, policy text, raw MCP frames, internal exceptions, tokens, or costs in customer responses.
- Existing `POST .../messages` and confirmation endpoints remain compatible.
- Reads may execute automatically; every database-changing retail tool requires a matching one-time confirmation fingerprint.
- An active human handoff blocks write confirmation but does not block customer-owned reads.
- Every conversation and handoff lookup is scoped to the authenticated owner; developer operations require the developer role.
- SSE completion is emitted only after durable persistence succeeds.
- No new runtime dependency is required.

## Review Focus

- SSE chunks split inside UTF-8 or JSON boundaries must still parse into exactly one event; pin this in Task 4 browser-parser tests.
- A client disconnect followed by the same request ID must not duplicate the user message; pin this in Task 3 API tests.
- Two developers claiming one ticket concurrently must yield one winner; pin this in Task 2 repository/service tests.
- A pending write created before handoff must not execute while handoff is active; pin this in Task 2 support-service tests.
- Model/MCP failure after partial streamed blocks must end with a safe error and history reconciliation; pin this in Tasks 3 and 4.

---

### Task 1: Typed Runtime Progress Events

**Files:**
- Create: `backend/app/agent/progress.py`
- Modify: `backend/app/agent/runtime.py`
- Modify: `backend/app/agent/session_service.py`
- Test: `backend/tests/agent/test_runtime_progress.py`
- Test: `backend/tests/agent/test_session_service.py`

**Interfaces:**
- Produces: `AgentProgressEvent(stage: ProgressStage, message: str, tool_name: str | None, completed: int | None, total: int | None)`.
- Produces: `ProgressSink = Callable[[AgentProgressEvent], None]` and `emit_progress(sink, event) -> None`.
- Extends: `run_until_blocked(..., progress_sink: ProgressSink | None = None)` and `AgentSessionService.auto_run(..., progress_sink: ProgressSink | None = None)`.
- Preserves: all current callers when `progress_sink` is omitted.

- [ ] **Step 1: Write failing progress-contract tests**

  Add tests asserting a multi-step read emits `planning`, a tool-specific stage before execution, `tool_completed` after execution, and `composing` before terminal response; no event payload contains raw arguments or tool result content.

- [ ] **Step 2: Run the focused tests and verify RED**

  Run: `./scripts/test_backend.sh -q backend/tests/agent/test_runtime_progress.py backend/tests/agent/test_session_service.py`

- [ ] **Step 3: Implement the typed no-op-compatible progress interface**

  Map `get_user_details` to `account_lookup`, `get_order_details` to `order_lookup`, and other safe reads to `tool_running`; expose localized stage messages without arguments. Derive order completed/total from trusted objective ledger and successful user-detail payloads.

- [ ] **Step 4: Run focused tests and existing runtime tests**

  Run: `./scripts/test_backend.sh -q backend/tests/agent/test_runtime_progress.py backend/tests/agent/test_runtime.py backend/tests/agent/test_session_service.py`

- [ ] **Step 5: Record checkpoint**

  Record passing commands and changed files in the plan checkbox log; no Git commit is possible because the workspace has no repository metadata.

### Task 2: Durable Human Handoff and Write Blocking

**Files:**
- Create: `backend/app/persistence/migrations/007_human_handoffs.sql`
- Create: `backend/app/support/handoff.py`
- Modify: `backend/app/persistence/models.py`
- Modify: `backend/app/persistence/sqlite.py`
- Modify: `backend/app/support/service.py`
- Modify: `backend/app/api/main.py`
- Test: `backend/tests/persistence/test_handoff_repository.py`
- Test: `backend/tests/support/test_handoff_service.py`
- Test: `backend/tests/e2e/test_support_restart_recovery.py`

**Interfaces:**
- Produces: `HumanHandoffRecord` with statuses `open | in_progress | resolved | cancelled`.
- Produces: `HumanHandoffService.create_or_get_active(...)`, `get_for_owner(...)`, `list_for_developer(...)`, `claim(...)`, `resolve(...)`, and `cancel(...)`.
- Produces: repository compare-and-set transition methods that return `bool` on status mismatch.
- Consumes: existing `UserRecord`, conversation ownership, transactions, audit-event repository, and authenticated developer identity.

- [ ] **Step 1: Write failing migration and repository tests**

  Assert schema creation, owner-scoped reads, active-ticket idempotency, persistence after restart, and one-winner atomic claim under competing transitions.

- [ ] **Step 2: Run repository tests and verify RED**

  Run: `./scripts/test_backend.sh -q backend/tests/persistence/test_handoff_repository.py`

- [ ] **Step 3: Implement migration, model, and repository**

  Add indexed foreign keys for conversation, owner, status, assignee, and timestamps. Use transaction-scoped compare-and-set updates for claim/resolve/cancel.

- [ ] **Step 4: Write failing service policy tests**

  Assert duplicate customer requests return one active ticket; unauthorized owners cannot read it; active handoff allows read turns but blocks `confirm_action` before retail execution; every status transition appends an audit event.

- [ ] **Step 5: Implement `HumanHandoffService` and support write guard**

  Keep handoff orchestration in `support/handoff.py`. Inject it into `SupportService`; check active status at confirmation time, not only when the write was proposed.

- [ ] **Step 6: Run Task 2 tests**

  Run: `./scripts/test_backend.sh -q backend/tests/persistence/test_handoff_repository.py backend/tests/support/test_handoff_service.py backend/tests/e2e/test_support_restart_recovery.py`

- [ ] **Step 7: Record checkpoint**

  Record the migration number, transition invariants, and passing tests.

### Task 3: Queue-Backed SSE and Handoff APIs

**Files:**
- Create: `backend/app/support/streaming.py`
- Create: `backend/app/api/handoffs.py`
- Modify: `backend/app/api/support.py`
- Modify: `backend/app/api/main.py`
- Modify: `backend/app/support/service.py`
- Test: `backend/tests/support/test_streaming.py`
- Test: `backend/tests/api/test_support_stream_api.py`
- Test: `backend/tests/api/test_handoff_api.py`
- Test: `backend/tests/api/test_role_authorization.py`

**Interfaces:**
- Produces: `SupportStreamEvent(event: str, event_id: int, data: dict)` and `encode_sse(event) -> bytes`.
- Produces: `stream_support_turn(...) -> AsyncIterator[bytes]` using an AnyIO worker and thread-safe queue.
- Adds: `POST /api/v1/support/conversations/{id}/messages/stream`.
- Adds customer: `POST|GET /api/v1/support/conversations/{id}/handoff`.
- Adds developer: `GET /api/v1/admin/handoffs`, `POST .../{ticket_id}/claim|resolve|cancel`.

- [ ] **Step 1: Write failing SSE encoding and ordering tests**

  Assert valid `id`, `event`, and one-line JSON `data`; accepted is first, completed is last, IDs increase, heartbeat is a comment, and progress contains no raw arguments.

- [ ] **Step 2: Run streaming tests and verify RED**

  Run: `./scripts/test_backend.sh -q backend/tests/support/test_streaming.py backend/tests/api/test_support_stream_api.py`

- [ ] **Step 3: Implement queue-backed streaming orchestration**

  Run the synchronous support turn in a worker thread, forward progress via a bounded queue, emit heartbeat comments while idle, map known exceptions to existing safe error codes, and emit completed only after the service transaction returns.

- [ ] **Step 4: Add disconnect and partial-failure tests**

  Assert cancellation is requested, duplicate request ID yields persisted prior output rather than duplicate messages, and model/MCP failure emits one safe terminal error followed by no completed event.

- [ ] **Step 5: Write failing customer/developer handoff API tests**

  Assert owner scoping, developer role enforcement, idempotent create, claim conflict, resolve/cancel transitions, and safe response schemas.

- [ ] **Step 6: Implement focused handoff router and app wiring**

  Keep developer routes out of the customer router. Reuse current authentication middleware and admin role checks.

- [ ] **Step 7: Run Task 3 tests**

  Run: `./scripts/test_backend.sh -q backend/tests/support/test_streaming.py backend/tests/api/test_support_stream_api.py backend/tests/api/test_handoff_api.py backend/tests/api/test_role_authorization.py`

- [ ] **Step 8: Record checkpoint**

  Record the public event schema and all endpoint paths.

### Task 4: Customer Stream Parser and Activity UI

**Files:**
- Create: `backend/app/static/support/stream.js`
- Modify: `backend/app/static/support/api.js`
- Modify: `backend/app/static/support/chat.js`
- Modify: `backend/app/static/support/app.js`
- Modify: `backend/app/static/support/index.html`
- Modify: `backend/app/static/support/styles.css`
- Test: `backend/tests/api/test_support_static.py`
- Create: `scripts/test_support_stream_parser.mjs`

**Interfaces:**
- Produces: `parseSSEStream(readable, onEvent) -> Promise<void>` that survives arbitrary UTF-8/chunk boundaries.
- Produces: `api.streamMessage(id, content, requestId, onEvent)`.
- Extends chat view with `beginActivity()`, `updateActivity(event)`, `appendStreamBlock(block, index)`, and `finishActivity()`.
- Consumes Task 3 event names and payload fields exactly.

- [ ] **Step 1: Write failing parser tests**

  Cover multiple events in one chunk, one event split across chunks, a multibyte Chinese character split across chunks, heartbeat comments, malformed data isolation, and one terminal callback.

- [ ] **Step 2: Run parser and static tests and verify RED**

  Run: `node scripts/test_support_stream_parser.mjs && ./scripts/test_backend.sh -q backend/tests/api/test_support_static.py`

- [ ] **Step 3: Implement fetch-based SSE parser and API client**

  Use one streaming `TextDecoder`, split frames on blank lines, join repeated `data:` lines, ignore comments, and parse event JSON without `innerHTML`.

- [ ] **Step 4: Implement activity row and incremental block rendering**

  Show server-provided localized stage, elapsed time, and optional completed/total. Keep the activity row last, insert blocks before it, and reconcile history on disconnect or terminal failure.

- [ ] **Step 5: Add frontend contract assertions**

  Assert the old JSON call is no longer used by the primary composer, activity has `role="status"` and `aria-live`, composer locking is stable, and raw internal labels are absent.

- [ ] **Step 6: Run Task 4 tests**

  Run: `node scripts/test_support_stream_parser.mjs && ./scripts/test_backend.sh -q backend/tests/api/test_support_static.py`

- [ ] **Step 7: Record checkpoint**

  Record parser cases and customer-visible stage copy.

### Task 5: Permission Disclosure and Human Transfer UX

**Files:**
- Modify: `backend/app/static/support/index.html`
- Modify: `backend/app/static/support/app.js`
- Modify: `backend/app/static/support/api.js`
- Modify: `backend/app/static/support/cards.js`
- Modify: `backend/app/static/support/styles.css`
- Modify: `backend/app/support/projector.py`
- Test: `backend/tests/support/test_projector.py`
- Test: `backend/tests/api/test_support_static.py`

**Interfaces:**
- Consumes: Task 2 customer handoff schema and Task 3 customer endpoints.
- Produces: permission disclosure states `查询自动执行`, `操作需确认`, `人工可接管`.
- Produces: one-operation confirmation card copy and transfer status block.

- [ ] **Step 1: Write failing projector and static UI tests**

  Assert confirmation blocks contain localized operation, affected order/items, changed values, one-time authorization copy, and distinct `确认执行`/`拒绝操作`. Assert permission panel and `转人工` command exist without nested cards.

- [ ] **Step 2: Run tests and verify RED**

  Run: `./scripts/test_backend.sh -q backend/tests/support/test_projector.py backend/tests/api/test_support_static.py`

- [ ] **Step 3: Implement safe confirmation projection**

  Translate known write tool names and allow-listed argument fields. Never display confirmation fingerprints, idempotency keys, policy text, or internal rationale.

- [ ] **Step 4: Implement permission details and transfer state**

  Use an inline collapsible disclosure, a clear transfer command, disabled duplicate request state, and persisted ticket status loaded with each active conversation.

- [ ] **Step 5: Run Task 5 tests**

  Run: `./scripts/test_backend.sh -q backend/tests/support/test_projector.py backend/tests/api/test_support_static.py backend/tests/api/test_handoff_api.py`

- [ ] **Step 6: Record checkpoint**

  Record confirmation disclosure fields and prohibited internal fields.

### Task 6: Developer Human-Handoff Console

**Files:**
- Modify: `backend/app/static/dashboard/index.html`
- Modify: `backend/app/static/dashboard/app.js`
- Modify: `backend/app/static/dashboard/styles.css`
- Test: `backend/tests/api/test_dashboard_static.py`
- Test: `backend/tests/api/test_handoff_api.py`

**Interfaces:**
- Consumes: Task 3 developer handoff list and transition APIs.
- Produces dashboard route: `?view=handoffs` with filter, list, detail, claim, resolve, and cancel controls.
- Preserves all existing dashboard routes and role redirect behavior.

- [ ] **Step 1: Write failing dashboard route tests**

  Assert navigation entry, isolated route panel, Chinese labels, status filters, safe conversation history rendering, claim/resolve/cancel controls, loading/empty/error states, and no customer write-confirm button.

- [ ] **Step 2: Run dashboard tests and verify RED**

  Run: `./scripts/test_backend.sh -q backend/tests/api/test_dashboard_static.py backend/tests/api/test_handoff_api.py`

- [ ] **Step 3: Implement handoff list and detail route**

  Follow the existing dashboard view-router pattern. Fetch only when the route is active, abort stale requests, and render all model/customer text with `textContent`.

- [ ] **Step 4: Implement atomic transition controls**

  Refresh detail and list after each transition; display conflict when another developer already claimed or resolved the ticket.

- [ ] **Step 5: Run Task 6 tests**

  Run: `./scripts/test_backend.sh -q backend/tests/api/test_dashboard_static.py backend/tests/api/test_handoff_api.py backend/tests/api/test_role_authorization.py`

- [ ] **Step 6: Record checkpoint**

  Record dashboard route and developer operations.

### Task 7: End-to-End Acceptance and Documentation

**Files:**
- Create: `scripts/validate_streaming_handoff_ui.mjs`
- Modify: `scripts/validate_product_stack.sh`
- Modify: `README.md`
- Modify: `docs/final_implementation_roadmap.md`
- Test: entire `backend/tests/` suite

**Interfaces:**
- Consumes all Task 1-6 public interfaces.
- Produces one repeatable acceptance command for customer streaming, confirmation, handoff, and developer resolution.

- [ ] **Step 1: Write the failing browser acceptance script**

  Exercise customer login, immediate accepted/progress event, incremental blocks for all-orders query, permission disclosure, staged write, reject with no state change, explicit handoff, blocked write confirmation, developer claim/resolve, and resumed write eligibility.

- [ ] **Step 2: Run acceptance and verify the expected first failure**

  Run: `BASE_URL=http://127.0.0.1:8020 node scripts/validate_streaming_handoff_ui.mjs`

- [ ] **Step 3: Repair only integration defects revealed by acceptance**

  Keep fixes within the owning Task 1-6 boundary and add a regression test before each repair.

- [ ] **Step 4: Run full automated verification**

  Run: `./scripts/test_backend.sh -q`

  Run: `./scripts/validate_product_stack.sh`

  Run: `BASE_URL=http://127.0.0.1:8020 node scripts/validate_support_ui.mjs`

  Run: `BASE_URL=http://127.0.0.1:8020 node scripts/validate_streaming_handoff_ui.mjs`

- [ ] **Step 5: Perform one real-model streaming query**

  With `dashscope/qwen3.8-max`, query all orders for the linked demo customer. Verify server-driven status within one second after acceptance, real order completed/total progress, at least one order block before completed, durable history, and absence of internal reasoning/policy/tool arguments.

- [ ] **Step 6: Update operator documentation**

  Document event schema, permission rules, human handoff lifecycle, startup command, verification commands, and recovery behavior. Do not include API keys or customer secrets.

- [ ] **Step 7: Final review checkpoint**

  Summarize changed files, test counts, browser acceptance evidence, remaining limitations, and service URLs. Because this workspace is not a Git repository, provide no commit or branch claim.
