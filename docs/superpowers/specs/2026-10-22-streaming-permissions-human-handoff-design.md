# Streaming Support, Permissions, and Human Handoff Design

## Context

The customer support center currently submits a message through a synchronous
JSON endpoint. A multi-order request can require several LLM and MCP turns and
take close to one minute, while the browser receives no server-side progress
until the whole turn completes. A local pending animation reduces ambiguity but
does not report real runtime activity and all result blocks arrive together.

The runtime already protects write tools with explicit confirmation,
fingerprinted arguments, idempotency keys, persisted pending actions, and audit
events. Those guarantees are not clearly explained in the customer interface,
and there is no durable human-handoff workflow for requests the Agent cannot or
should not finish.

This design adds observable streaming without exposing private chain-of-thought,
makes permission boundaries explicit, and introduces a durable human-in-the-loop
queue in the engineering console.

## Goals

- Stream real operational progress for customer messages.
- Deliver customer-visible blocks as soon as they become available.
- Preserve the existing non-streaming endpoint for compatibility.
- Show clear read/write permission rules and one-operation confirmation scope.
- Let customers request human help and let the Agent escalate recoverable
  failures or unsupported requests.
- Provide developers with a durable human-handoff queue and auditable status
  transitions.
- Keep all data scoped to the authenticated customer and current conversation.

## Non-goals

- Do not expose hidden model reasoning, chain-of-thought, raw prompts, policy
  text, or tool arguments that contain internal-only data.
- Do not stream raw LLM planner JSON or MCP protocol frames to customers.
- Do not grant blanket approval for future writes or combine unrelated write
  operations into one confirmation.
- Do not build staffing, assignment schedules, chat between multiple agents, or
  external ticket-system integration in this phase.
- Do not remove the existing JSON message endpoint or existing confirmation API.

## Chosen Architecture

### 1. POST streaming protocol

Add:

```text
POST /api/v1/support/conversations/{conversation_id}/messages/stream
Content-Type: application/json
Accept: text/event-stream
```

The request body reuses `SupportMessageRequest`. The response is an SSE stream
consumed with `fetch()` and a readable stream, because browser `EventSource`
cannot POST a JSON body.

Every event has an SSE `event` name and a JSON `data` object:

| Event | Required data | Meaning |
| --- | --- | --- |
| `accepted` | `conversation_id`, `request_id` | Request ownership and idempotency validated. |
| `progress` | `stage`, `message`, optional `tool_label`, `completed`, `total` | Safe operational status. |
| `block` | serialized `SupportMessageBlock` | A customer-visible message or business card. |
| `confirmation_required` | `action_id`, serialized confirmation block | A write is staged and blocked. |
| `handoff` | `ticket_id`, `status`, `message` | Human assistance was requested. |
| `error` | `code`, `message`, `recoverable` | Structured safe error. |
| `completed` | `pending_action_id`, `block_count` | The turn is durably committed. |

SSE frames include monotonically increasing per-request `id` values. A
heartbeat comment is sent during long provider waits so intermediaries and the
browser can distinguish an active request from a dead connection.

### 2. Runtime progress bridge

Introduce a small typed progress interface in the Agent layer. Runtime and tool
execution boundaries emit semantic events such as:

- `planning`: understanding the request;
- `account_lookup`: reading the authenticated customer's account;
- `order_lookup`: reading one known order, with completed/total counts when
  available;
- `tool_completed`: a safe localized tool label, never raw arguments;
- `composing`: preparing the customer response;
- `awaiting_confirmation`: a write is staged;
- `handoff_requested`: automation stopped for human assistance.

The streaming API runs the synchronous Agent turn in a worker thread. A
thread-safe queue carries progress events to the async SSE generator. The
generator emits heartbeats while the queue is idle and terminates only after the
worker reports completion or failure.

The progress interface is optional and defaults to a no-op, so evaluation,
regression, CLI, and the existing JSON API keep their current behavior. Progress
events are descriptions of executed stages, not generated reasoning.

### 3. Incremental business blocks

Tool results are projected with the existing support projector. Read results
that are safe for the customer are emitted as `block` events after successful
tool execution. The final transaction remains authoritative:

1. The user message and all assistant blocks are written atomically.
2. The `completed` event is sent only after commit.
3. If persistence fails, the stream emits an `error`; the UI reloads history and
   treats only persisted messages as final.

The UI de-duplicates streamed blocks by request-local block index when history
is reloaded. Existing request-id idempotency prevents a reconnect retry from
creating a second user message.

### 4. Customer progress UI

Replace the fixed pending bubble with an in-stream activity row driven by SSE.
It contains:

- a restrained activity indicator;
- the current localized stage;
- elapsed time;
- optional order progress such as `正在读取订单 2/4`;
- a connection-recovery message if the stream disconnects.

Each incoming `block` is appended immediately above the activity row. The row is
removed on `completed`, `confirmation_required`, `handoff`, or terminal `error`.
The composer remains disabled while one turn is active to prevent concurrent
mutation of the same conversation.

The page never displays “思维链”, hidden reasoning, raw planner output, policy
prompts, or MCP payloads. Customer-facing wording describes actions actually
being performed.

### 5. Permission presentation and confirmation scope

Add a compact permission disclosure near the composer with three states:

- `查询自动执行`: profile, orders, products, and shipment reads;
- `操作需确认`: cancellation, address/payment modification, return, exchange;
- `人工可接管`: customer-requested or system-triggered escalation.

The disclosure opens an unframed details panel rather than a modal that blocks
chat. Confirmation cards continue to be the only authorization mechanism for a
write. Each card must show:

- localized operation name;
- affected order and item identifiers;
- changed fields and proposed values;
- a statement that confirmation authorizes this operation once;
- `确认执行` and `拒绝操作` commands.

The existing fingerprint remains the authorization identity. Any argument
change creates a different fingerprint and requires a new confirmation. Buttons
are disabled during submission; atomic pending-action transitions and
idempotency keys prevent double execution.

### 6. Durable human handoff

Add a `human_handoffs` table with:

- `ticket_id` primary key;
- `conversation_id` and `owner_user_id` foreign keys;
- `reason`, `customer_message`, and safe context summary;
- status: `open`, `in_progress`, `resolved`, or `cancelled`;
- optional `assigned_developer_user_id`;
- `created_at`, `updated_at`, and `resolved_at`.

Add customer APIs to create and read the current conversation's handoff. A
customer can press `转人工` or the runtime can create a handoff after an
unsupported request, repeated safe failure, or an explicit transfer decision.
Creation is idempotent while an open/in-progress ticket exists.

When a ticket is open or in progress:

- the Agent may continue answering read-only questions;
- no new write operation may execute;
- an already staged confirmation remains visible but confirmation is blocked
  until the ticket is resolved or cancelled;
- the UI clearly shows that a human is handling account-changing requests.

The dashboard receives a dedicated `人工接管` route. Developers can filter
tickets, inspect customer-visible conversation history and safe runtime errors,
claim an open ticket, mark it resolved, or cancel an invalid ticket. Every
transition writes an audit event. Developer role enforcement uses the existing
authentication middleware and admin authorization boundary.

### 7. Error and reconnect behavior

- Authentication and ownership are checked before the first `accepted` event.
- Model quota, provider, MCP, database, and validation failures retain distinct
  safe error codes.
- Client disconnect requests cancellation of the stream worker when safe; an
  in-flight external call may finish, but commit semantics remain atomic.
- The browser retries history retrieval after a disconnect. It may resubmit the
  same request ID only when no persisted user message exists.
- A failed stream is recorded in runtime issues and can be converted into a
  human-handoff ticket from the error UI.
- Heartbeats contain no business data and are not stored as messages.

## Data Flow

1. The customer submits a message with a stable request ID.
2. The streaming endpoint validates login, role, ownership, and duplicates.
3. It starts the Agent turn in a worker and immediately emits `accepted`.
4. Runtime callbacks emit safe stage updates through a thread-safe queue.
5. Successful read results are projected and streamed as customer blocks.
6. A write proposal stops at the existing policy guard and emits a confirmation
   block; no write tool executes.
7. Support persistence commits the user message, blocks, pending action, state,
   telemetry, and audit evidence.
8. The endpoint emits `completed`; the browser refreshes the conversation index.
9. A later explicit confirmation uses the existing confirmation endpoint and
   follows the same one-operation fingerprint and idempotency rules.

## Security and Privacy

- Conversation and ticket access is always scoped by authenticated owner ID.
- Customer streams cannot expose developer-only trace, policy, token, cost, raw
  exception, prompt, or tool argument data.
- Read permissions do not imply write permissions.
- Handoff creation does not grant the developer a customer session; dashboard
  operations use the developer's own authenticated identity.
- Confirmation and handoff transitions are server-authoritative and audited.
- SSE payloads use JSON serialization and browser rendering uses `textContent`.

## Testing Strategy

### Runtime and service

- Progress callbacks preserve event order and remain optional.
- Multi-order lookup reports real completed/total progress.
- Existing non-streaming service behavior remains unchanged.
- A staged write emits confirmation and never executes before approval.
- An argument change requires a new confirmation fingerprint.
- Open human handoff blocks write confirmation but allows reads.
- Duplicate handoff requests return the existing active ticket.

### API and persistence

- Streaming endpoint emits valid SSE accepted, progress, block, and completed
  frames in order.
- Quota, MCP, and database failures emit safe terminal error events.
- Disconnect/retry with one request ID does not duplicate messages.
- Handoff repository supports atomic open, claim, resolve, and cancel
  transitions.
- Customer ownership and developer role access are enforced.

### Frontend

- Fetch stream parser handles arbitrary chunk boundaries and multi-line frames.
- Activity row updates in place and shows elapsed time.
- Business blocks render before completion.
- Permission details and one-operation confirmation copy are present.
- Transfer button creates one ticket and renders its status.
- Dashboard route lists and updates handoff tickets.
- Mobile and desktop layouts contain no overlap or clipped controls.

### Verification

- Run focused red-green tests for every layer.
- Run the full backend suite.
- Run existing support and product-stack acceptance scripts.
- Run browser acceptance for read streaming, write confirmation/rejection,
  reconnect, explicit handoff, and developer resolution.
- Perform one real `qwen3.8-max` multi-order query and verify incremental status
  and customer blocks without exposing internal reasoning.

## Acceptance Criteria

- The customer sees a server-driven status within one second of message
  acceptance.
- A four-order lookup shows real order progress and at least one business block
  before the final completion event.
- No private reasoning, prompt, policy, raw MCP frame, or internal exception is
  visible in customer HTML or stream payloads.
- Every write remains blocked until a matching one-time confirmation succeeds.
- Rejecting an action never changes retail state.
- Customers can request human assistance and see its current status.
- Developers can claim and resolve tickets from a separate dashboard page.
- An active handoff prevents automated writes and records all transitions.
- Existing JSON clients, evaluation runs, regression runs, and tests remain
  compatible.

## Files Expected to Change

- `backend/app/agent/`: progress event contract and runtime emission.
- `backend/app/support/`: streaming orchestration, projection, and handoff rules.
- `backend/app/api/support.py`: SSE and customer handoff endpoints.
- `backend/app/api/admin.py` or a focused handoff router: developer APIs.
- `backend/app/persistence/`: migration 007 and handoff repository.
- `backend/app/static/support/`: stream parser, activity UI, permissions, and
  transfer controls.
- `backend/app/static/dashboard/`: human-handoff route and queue UI.
- `backend/tests/`: unit, API, persistence, frontend contract, and end-to-end
  coverage.
- `scripts/`: browser acceptance for streaming and handoff flows.
