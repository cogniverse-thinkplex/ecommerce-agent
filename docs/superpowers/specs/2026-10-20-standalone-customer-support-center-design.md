# Standalone Customer Support Center Design

## 1. Status and intent

This specification defines the next product milestone for the adaptive e-commerce agent: a locally runnable, customer-facing support center that is complete enough for real demonstrations and hands-on use.

The existing `/dashboard/` remains an internal engineering and evaluation console. A new `/support/` application becomes the customer surface. Both surfaces share the same agent runtime, policy guard, audit pipeline, and retail tools.

The milestone is considered approximately 90% of a local quasi-product. Production commerce integrations, cloud orchestration, enterprise identity, and advanced long-term memory remain outside this scope.

## 2. Goals

- Provide a standalone Chinese customer-support web application.
- Support identity verification by email or by name plus ZIP code.
- Support profile, order, and product information queries.
- Support guarded order cancellation and modification, returns, exchanges, and default-address updates.
- Require explicit confirmation before every database-changing action.
- Persist sessions, messages, authentication state, pending confirmations, execution results, and audit summaries across restarts.
- Add a real MCP-backed retail tool option while preserving the existing tau2 Python backend for evaluation.
- Keep local startup simple through Conda and add a Docker Compose path.
- Verify critical flows with unit, API, integration, browser, responsive-layout, and restart-recovery tests.

## 3. Non-goals

- Kubernetes or public-cloud deployment.
- Multi-tenant enterprise authorization and SSO.
- Integration with a real payment processor, warehouse, carrier, or production commerce database.
- A production human-agent platform integration.
- Vector-store-backed long-term memory or a complete RAG platform.
- Automatic model training or self-modifying source code.
- Replacement of the current tau2 benchmark and evaluation workflow.

## 4. System architecture

### 4.1 User and engineering surfaces

The FastAPI application exposes two separately mounted static applications:

- `/support/`: customer-facing support center.
- `/dashboard/`: internal development, benchmark, cost, audit, and debugging console.

The support center must not expose prompts, policy text, tool names, raw tool arguments, reward, cost, benchmark tasks, or raw traces. It consumes a purpose-built support API that maps internal runtime state into stable user-facing resources.

The dashboard keeps its current APIs and behavior. Existing evaluation scripts continue to construct an in-memory session service unless explicitly configured otherwise, so benchmark reproducibility does not silently depend on local application data.

### 4.2 Backend boundaries

The existing components remain authoritative:

- `AgentRuntime`: plans and advances one conversational turn.
- `AgentSessionService`: coordinates sessions and runtime execution.
- `GuardedRetailToolExecutor`: enforces confirmation and records before/after state evidence.
- `RetailToolPort`: isolates the runtime from a concrete retail tool backend.
- `SessionAudit`: derives reviewable write-operation evidence.

New components add product concerns without embedding them in the runtime:

- `SupportService`: user-facing application service for conversation lifecycle and response projection.
- `ConversationRepository`: persists conversations and authentication state.
- `MessageRepository`: persists ordered user, assistant, system, and action messages.
- `PendingActionRepository`: persists confirmation-safe write proposals and terminal outcomes.
- `AuditRepository`: persists immutable support-facing audit snapshots or events.
- `SqliteUnitOfWork`: owns SQLite transactions and schema initialization.
- `McpRetailAdapter`: implements `RetailToolPort` through an MCP client.
- `RetailMcpServer`: exposes the retail tool catalogue through MCP while delegating to the tau2 retail implementation for local data semantics.

Repository protocols prevent persistence details from leaking into agent nodes. SQLite is the default implementation; a future PostgreSQL implementation can replace it without changing support APIs or runtime logic.

### 4.3 Dependency construction

Application startup constructs dependencies from environment settings:

- `ECOM_AGENT_STORE=sqlite` for the support application.
- `ECOM_AGENT_SQLITE_PATH=./data/ecommerce_agent.db` by default.
- `ECOM_AGENT_TOOL_BACKEND=mcp` for the quasi-product path.
- `ECOM_AGENT_TOOL_BACKEND=tau2_python` for direct benchmark and fallback operation.
- MCP endpoint and timeout settings are separate from model settings.

Tests can inject repositories and tool ports directly. Evaluation code retains explicit construction of `TauRetailAdapter` where deterministic direct execution is required.

## 5. Data model and persistence

### 5.1 SQLite choice

SQLite is the default because the target is a local quasi-product and should run without installing a database server. The database uses WAL mode, foreign keys, explicit transactions, and schema migrations. The data directory is bind-mounted in Docker Compose.

### 5.2 Core records

`conversations`:

- stable UUID, display title, lifecycle status, created/updated timestamps
- authenticated retail user identifier and authentication method
- serialized runtime checkpoint or a reconstructable runtime-state payload
- last error category and recovery metadata

`messages`:

- stable UUID, conversation ID, monotonic sequence number
- role and message kind
- user-visible text and optional structured presentation payload
- delivery state and timestamps

`pending_actions`:

- stable action UUID and conversation ID
- tool intent, normalized arguments, fingerprint, and idempotency key
- localized confirmation summary
- status: `pending`, `confirmed`, `rejected`, `executing`, `succeeded`, or `failed`
- execution result, failure category, created/resolved timestamps

`audit_events`:

- stable event UUID, conversation/action IDs
- event type, structured evidence payload, timestamp
- immutable append-only semantics

`schema_migrations`:

- migration version and application timestamp

### 5.3 Consistency and recovery

- A user message and the resulting persisted runtime checkpoint commit atomically when possible.
- Creating a pending write action and its confirmation card is one transaction.
- Confirmation uses a compare-and-set status transition, so retries cannot execute an action twice.
- The idempotency key is unique per normalized mutation.
- On startup, actions left in `executing` are marked recoverable and are not automatically replayed.
- Stored presentation payloads are projections, not sources of authority; the guard and tool result remain authoritative.

## 6. Support API

The customer application uses versioned endpoints under `/api/v1/support`:

- `POST /conversations`: create a conversation.
- `GET /conversations`: list resumable conversations.
- `GET /conversations/{id}`: return conversation summary and current status.
- `DELETE /conversations/{id}`: archive a conversation, without deleting audit evidence.
- `GET /conversations/{id}/messages`: return paginated user-visible messages.
- `POST /conversations/{id}/messages`: submit one user message and return the resulting messages or pending action.
- `POST /conversations/{id}/actions/{action_id}/confirm`: explicitly confirm one pending mutation.
- `POST /conversations/{id}/actions/{action_id}/reject`: reject one pending mutation.
- `POST /conversations/{id}/retry`: retry the latest recoverable non-mutating failure.
- `GET /health`: report application, database, model, and tool-backend availability without secrets.

Responses use structured message blocks:

- `text`
- `authentication_request`
- `order_summary`
- `product_summary`
- `profile_summary`
- `confirmation`
- `operation_result`
- `transfer_status`
- `recoverable_error`

The API returns stable error codes and Chinese user-safe messages. Internal exceptions, prompts, raw arguments, and stack traces are logged but not sent to the browser.

## 7. Customer interface

### 7.1 Technology and file structure

The first implementation uses modular vanilla HTML, CSS, and JavaScript served by FastAPI. This avoids adding a second build chain while the interaction contract is still stabilizing. Modules remain small and framework-neutral so a later React migration can preserve the API and state model.

Proposed modules:

- `static/support/index.html`: semantic application shell.
- `static/support/styles.css`: responsive visual system and component states.
- `static/support/app.js`: startup and top-level orchestration.
- `static/support/api.js`: typed request helpers and error normalization.
- `static/support/session.js`: active conversation and persisted client preference.
- `static/support/chat.js`: message rendering, submission, and scrolling.
- `static/support/cards.js`: order, product, profile, result, and confirmation blocks.
- `static/support/history.js`: conversation list and mobile drawer.

### 7.2 Layout and interaction

Desktop layout has a compact conversation-history rail and a primary chat workspace. Mobile layout converts history into a drawer and keeps the composer reachable without covering messages.

The header shows the service name, connection state, and current authenticated-customer state. The message stream renders user and assistant messages plus structured business cards. The composer supports multiline text, send, disabled, pending, and retry states.

Authentication is conversational but rendered with an accessible form block when required. Users can authenticate with email or switch to name plus ZIP code. The browser never accepts or displays an arbitrary user ID as authentication proof.

Mutation proposals render as confirmation cards containing all material details. Confirm and reject controls become disabled immediately after use and are replaced by progress and final-result states. No optimistic success message is shown before tool execution and state verification finish.

### 7.3 Accessibility and responsive behavior

- Keyboard-accessible navigation and controls.
- Visible focus treatment and semantic labels.
- Live regions for new assistant messages and operation status.
- Sufficient contrast and no color-only status communication.
- Stable dimensions for the composer and action controls.
- No horizontal overflow at supported mobile widths.
- Reduced-motion support for nonessential transitions.

## 8. Agent and tool data flow

### 8.1 Read request

1. The browser submits a user message.
2. `SupportService` validates conversation ownership and writes the message.
3. `AgentSessionService` advances the runtime.
4. The planner responds or requests at most one tool call.
5. `GuardedRetailToolExecutor` delegates a permitted read to `RetailToolPort`.
6. The result is converted into user-facing text and structured cards.
7. Runtime checkpoint, messages, and audit events are committed.

### 8.2 Write request

1. The runtime proposes a normalized mutation.
2. The guard validates authentication, scope, policy, and arguments.
3. The system persists a pending action and confirmation card; no mutation runs.
4. The user explicitly confirms or rejects that action.
5. Confirmation performs an atomic pending-to-executing transition.
6. The guard revalidates fingerprint, arguments, conversation, and authenticated user.
7. The selected retail backend executes the mutation once.
8. Before/after database hashes or equivalent evidence determine whether state changed.
9. The terminal action state, result message, checkpoint, and audit event are committed.

### 8.3 Authentication and scope

Every conversation authenticates exactly one retail user before private information is returned. Once authenticated, attempts to act on another user's records are denied. A conversation cannot switch to another retail user; the user must start a new conversation.

## 9. MCP tool backend

### 9.1 Adapter contract

`McpRetailAdapter` implements the current `RetailToolPort` contract. It discovers or validates the expected retail tool catalogue during startup, maps local invocation objects to MCP calls, normalizes MCP results, and reports backend metadata as MCP-managed.

The adapter applies timeouts and classifies transport, protocol, tool, and validation failures. It does not implement policy or confirmation logic; those remain in `GuardedRetailToolExecutor` so direct and MCP backends behave consistently.

### 9.2 Local MCP server

The local `RetailMcpServer` exposes the same retail operations currently available through `TauRetailAdapter`. The server delegates to the tau2 retail environment and returns structured content suitable for lossless adapter normalization.

The initial transport is Streamable HTTP because the quasi-product and Docker Compose run the API and tool service as separate processes. The MCP service binds to an internal or loopback address by default. No API key or model secret is exposed to it.

### 9.3 Compatibility and fallback

- Startup fails clearly when `mcp` is configured and required tools are missing.
- The product does not silently fall back from MCP to direct execution after a write request.
- Developers can explicitly choose `tau2_python` for offline or benchmark work.
- Contract tests run the same read/write scenarios against both adapters.

## 10. Error handling and security properties

- Model failure returns a recoverable response and never fabricates commerce data.
- MCP disconnection preserves the conversation and pending action for deliberate retry.
- Database failures roll back the current transaction and return a stable error code.
- Duplicate message submissions use request IDs to avoid duplicated turns.
- Duplicate confirmations cannot execute the mutation twice.
- Rejected, failed, and successful writes all remain visible in audit history.
- Secrets are loaded from environment variables and are not rendered in either web surface.
- Logs redact API keys and user-sensitive tool arguments where possible.
- Support APIs validate identifiers and do not expose arbitrary filesystem or backend access.
- Human transfer follows the retail policy sequence and reports unavailable integration honestly in local mode.

## 11. Local operation and packaging

### 11.1 Conda development path

The existing Conda environment remains supported. A single documented command starts the MCP server and API, either through a helper script or a small process supervisor. SQLite schema initialization is automatic and idempotent.

### 11.2 Docker Compose path

Docker Compose defines:

- `api`: FastAPI application and static support/dashboard assets.
- `retail-mcp`: local retail MCP service.
- a named volume or bind mount for SQLite data.

Health checks gate service readiness. Environment variables are sourced from a local `.env`; example files contain no working secret. The API is exposed on port 8000 by default, with `/support/` as the primary user entry point.

## 12. Testing and validation

### 12.1 Automated backend tests

- Repository tests for migrations, ordering, transaction rollback, restart recovery, and compare-and-set transitions.
- Support API tests for lifecycle, pagination, authentication projection, mutation confirmation, rejection, idempotency, and safe errors.
- MCP adapter and server contract tests for catalogue parity and normalized results.
- Existing runtime, guard, audit, dashboard, and benchmark tests remain green.

### 12.2 End-to-end flows

At minimum, automated browser tests cover:

1. Create conversation, authenticate, query an order, and render an order card.
2. Propose a cancellation, inspect confirmation details, confirm, and see verified success.
3. Propose a mutation and reject it; verify no state change.
4. Reload the browser and resume persisted history.
5. Restart the API and resume the same conversation.
6. Disconnect MCP and receive a recoverable failure without a false success.
7. Attempt cross-user access and receive a policy denial.

### 12.3 Visual checks

Desktop and mobile screenshots verify that the message stream, cards, composer, history navigation, confirmation controls, and error states do not overlap or overflow. Browser checks also verify keyboard focus and that the primary flow remains usable at narrow widths.

## 13. Delivery sequence

Implementation proceeds in five substantial milestones rather than many small demonstration-only increments:

1. Persistence foundation and support-facing API contracts.
2. Complete customer-support web interface wired to real runtime state.
3. MCP retail server and adapter with backend parity tests.
4. Docker Compose, startup tooling, restart recovery, and end-to-end tests.
5. Responsive polish, accessibility, failure-state hardening, documentation, and full regression validation.

Each milestone must include implementation, focused tests, and integration verification before the next milestone begins. Demonstration-only fake business results are not accepted.

## 14. Acceptance criteria

The milestone is complete when:

- A user can open `/support/`, create and resume conversations, authenticate, and complete supported retail workflows without using the engineering dashboard.
- All displayed business information originates from the configured retail backend.
- Every mutation requires a persisted, explicit confirmation and produces auditable execution and state-verification evidence.
- Restarting the browser or API does not lose completed conversation history or pending user decisions.
- MCP is a real selectable backend and passes parity scenarios with the direct tau2 adapter.
- Conda startup and Docker Compose startup are both documented and verified.
- The full automated test suite and local validation script pass.
- Desktop and mobile browser validation shows no blocking layout or interaction defects.

## 15. Deferred final 10%

The remaining productionization work includes PostgreSQL or managed persistence, enterprise authentication, permissions and tenant isolation, real commerce and human-support integrations, observability infrastructure, cloud deployment, disaster recovery, load testing, security review, and advanced memory or retrieval systems.
