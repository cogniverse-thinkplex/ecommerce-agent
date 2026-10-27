# E17 Order ID Recovery and Write Plan UI Design

## Context

E16 introduced a structured `write_plan` and completed tau2 Retail task 59 with
both required writes. The run still used nine tool actions and produced three
`Order not found` responses before the model retried with the canonical order
identifier. The dashboard exposes the conversation trace and pending write, but
does not expose the plan that now drives multi-write execution.

E17 makes order lookup tolerant of a narrow class of model formatting errors and
makes the existing plan visible in the Chinese test console. It must preserve the
current confirmation, policy, fingerprint, order-lock, and audit guarantees.

## Goals

- Canonicalize recognizable tau2 Retail order identifiers before a read-only
  `get_order_details` proposal is validated or executed.
- Canonicalize order identifiers stored in the initial structured `write_plan`.
- Recover from a failed order lookup by steering the next planner turn toward the
  pending plan objective and the authenticated user's observed orders.
- Display the structured write plan in the Chinese dashboard with current,
  pending, and completed states.
- Re-run task 59 with `dashscope/qwen3.8-flash` and verify that confirmed business
  outcome remains correct while avoidable lookup errors disappear.

## Non-goals

- Do not rewrite arguments for write tools such as `cancel_pending_order` or
  `modify_pending_order_address`.
- Do not infer arbitrary identifiers, fuzzy-match malformed strings, or read
  benchmark expected actions to repair a proposal.
- Do not make the write plan editable in the dashboard.
- Do not add a new API endpoint when the existing session endpoint already
  returns `objective_ledger.write_plan`.
- Do not change tau2's adapter or upstream benchmark data.

## Chosen Architecture

### 1. Pure order identifier canonicalizer

Add a small agent-layer helper with this contract:

```python
canonicalize_retail_order_id(value: object) -> str | None
```

The helper trims surrounding whitespace and accepts only `#?W` followed by one
or more decimal digits, case-insensitively. A valid value is returned as
`#W<digits>`. Non-strings, empty strings, and all other shapes return `None`.
The function does not consult benchmark data or mutate caller-owned objects.

Examples:

| Input | Result |
| --- | --- |
| `W8268610` | `#W8268610` |
| `#w8268610` | `#W8268610` |
| `  #W8268610  ` | `#W8268610` |
| `8268610` | `None` |
| `W82-68610` | `None` |

### 2. Proposal-boundary normalization

After planner output has been parsed, but before schema validation, normalize
`arguments.order_id` only when `tool_name == "get_order_details"`. If a valid
canonical value differs from the proposal, replace it in a copied arguments
mapping and emit `planner.order_id_normalized` with `tool_name`, `original`, and
`normalized` fields.

Malformed values remain unchanged so the normal validation/execution path can
report the real error. Write-tool proposals never enter this normalization path,
even when they contain a recognizable non-canonical identifier. This preserves
the exact operation shown to the user and confirmed by fingerprint.

### 3. Write-plan normalization

When the first planner decision initializes `objective_ledger.write_plan`, apply
the same helper to each optional objective `order_id`. A recognizable identifier
is stored canonically. An absent or malformed identifier is stored as `None`, so
it cannot create a false lock. Existing plans remain immutable on later turns.
The existing maximum of eight objectives and allowed-write-tool validation stay
unchanged.

### 4. Plan-aware lookup recovery

Recovery remains planner-facing rather than executing an unrequested tool. The
runtime derives a compact lookup hint from trusted session state:

1. Select the first pending `write_plan` objective.
2. Prefer its canonical `order_id` when it has not been successfully inspected.
3. Otherwise consider canonical order IDs observed in a successful
   `get_user_details` payload, excluding successfully inspected IDs.
4. Never use expected benchmark actions, task fixtures, or a failed tool payload
   as a source of truth.

When `get_order_details` returns `Order not found`, record the failed canonical
identifier in runtime context and include the lookup hint in the next planner
prompt. The hint explicitly says not to retry a failed ID unless newer trusted
state identifies it as the current objective. The runtime does not autonomously
execute the fallback and does not change a write proposal.

Successful order reads continue to populate `inspected_order_ids`. Failed reads
must not be marked inspected. Repeated-read detection remains order-aware.

### 5. Dashboard plan panel

Add an unframed subsection named `写操作计划` inside the existing `对话测试台`.
`loadTrace(conversationId)` fetches the trace and session state in parallel and
passes `session.objective_ledger.write_plan` to `renderWritePlan(plan)`.

Each objective row displays:

- a Chinese status label: `当前`, `待处理`, or `已完成`;
- a Chinese tool label with the original tool name available as secondary text;
- the order identifier when present;
- the objective intent when present.

The first pending objective is `当前`; later pending objectives are `待处理`.
Completed objectives are `已完成`. An empty plan displays
`暂无结构化写操作计划`. The panel is read-only and responsive, with stable row
layout and no nested card styling.

If the session fetch fails because the conversation does not yet exist, trace
loading retains its current behavior and the plan renders empty. Other request
errors continue through the dashboard's existing error handling.

## Data and Event Flow

1. The LLM returns a planner decision and optional first-turn `write_plan`.
2. Runtime normalizes valid plan metadata and initializes the objective ledger.
3. For a `get_order_details` decision, runtime normalizes a recognizable read
   argument and emits an audit event if it changed.
4. Existing proposal validation, policy routing, MCP-managed tool execution, and
   state recording run unchanged.
5. A failed lookup contributes a recovery hint to the next LLM context; a
   successful lookup contributes a trusted inspected order.
6. The dashboard fetches trace and session state, rendering conversation events,
   pending confirmation, and write-plan progress together.

## Safety and Error Handling

- Automatic mutation is restricted to read proposals and plan metadata.
- Write arguments, confirmation fingerprints, and confirmed payloads remain
  byte-for-byte derived from the model proposal and existing policy flow.
- Canonicalization is allow-list based; malformed input is not guessed.
- Recovery can suggest only IDs already present in the plan or successful user
  tool output.
- No direct tau2 environment access is added outside the existing MCP-managed
  tool port.
- Audit events make every changed read argument visible in session traces.

## Testing Strategy

### Unit and runtime tests

- Canonicalizer accepts missing `#`, lowercase `w`, canonical input, and outer
  whitespace.
- Canonicalizer rejects missing `W`, punctuation, empty values, and non-strings.
- `get_order_details` is normalized before validation and emits one audit event.
- A write proposal with the same non-canonical value is not modified.
- Initial plan objectives are normalized; malformed IDs become unknown and do
  not establish an order lock.
- A failed lookup produces a plan-aware hint without marking the ID inspected.
- Recovery excludes successfully inspected and previously failed IDs when a
  different trusted candidate exists.
- Existing write-plan advancement, lock handoff, and confirmation tests remain
  green.

### Dashboard tests

- Static dashboard contains the Chinese plan heading and empty-state copy.
- JavaScript fetches session state and trace together.
- Rendering includes all three Chinese status labels and escapes model content.
- Existing pending-confirmation controls remain present.

### Verification gates

- Run focused tests after each red-green cycle.
- Run the full backend test suite and `scripts/validate_local.sh`.
- Run all existing E9-E16 artifact gates.
- Re-run tau2 Retail task 59 once with `dashscope/qwen3.8-flash`.

## Acceptance Criteria

- All automated tests and local validation pass.
- Task 59 reaches confirmed outcome success `1/1` and performs both required
  writes on their intended orders.
- The task 59 artifact contains zero `get_order_details` executions ending in
  `Order not found`.
- The task completes in at most seven tool actions unless provider output causes
  an unrelated, documented deviation.
- The dashboard shows the session's structured plan in Chinese and updates after
  turns and confirmations.
- No write proposal argument is silently normalized.

## Files Expected to Change

- `backend/app/agent/`: canonicalizer and runtime integration.
- `backend/tests/agent/`: canonicalization and recovery behavior tests.
- `backend/app/static/dashboard/index.html`: plan subsection markup.
- `backend/app/static/dashboard/app.js`: session fetch and plan rendering.
- `backend/app/static/dashboard/styles.css`: responsive plan status styling.
- `backend/tests/api/test_dashboard_static.py`: dashboard contract tests.
- `docs/smoke/`: E17 real-model regression report after implementation.

