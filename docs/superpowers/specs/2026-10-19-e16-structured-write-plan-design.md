# E16 Structured Write Plan Design

## Goal

Represent multi-write customer objectives as an explicit runtime plan so the agent can finish each requested mutation exactly once, preserve dependencies, and resume after confirmation without reconstructing the entire objective from conversation history.

## Scope

E16 extends the existing `ObjectiveLedger`, planner decision contract, runtime bookkeeping, and evaluation evidence. It does not replace the Guard, change tool schemas, trust benchmark expected actions, or introduce task-specific routing.

## State Model

Add a `WriteObjective` model with:

- `objective_id`: planner-generated identifier, normalized and made unique by runtime.
- `tool_name`: one allowed write tool name.
- `order_id`: optional target order known during planning.
- `intent`: concise natural-language description used only as planner context.
- `status`: `pending` or `completed`.
- `completed_fingerprint`: populated only after a successful real write execution.

`ObjectiveLedger` gains `write_plan: list[WriteObjective]`. The list preserves order and allows repeated tool names because a request can contain multiple mutations of the same kind.

## Planner Contract

`PlannerDecision` accepts an optional `write_plan` alongside its normal action. The planner may provide this plan only when the ledger has no existing plan. Each entry must reference a write tool from `AVAILABLE_TOOLS`; unknown, read-only, malformed, and excess entries are discarded by runtime validation.

The plan is a navigation hint, not execution authority. It cannot mark entries completed, provide confirmation, bypass policy, or prove that the customer requested an operation. Tool proposals still pass through skill policy, proposal validation, fingerprint confirmation, and the guarded executor.

Once a plan exists, the planner receives the full compact plan plus an explicit `NEXT_WRITE_OBJECTIVE`. It should resolve only the reads required for that objective, propose its write, and then continue to the next pending objective after successful execution.

## Trusted Progression

Runtime records a plan only from a parsed planner decision and emits `objective_plan.created`. It never reads tau2 task IDs or expected actions.

Successful write execution remains the sole completion signal. `record_tool_execution` matches the first pending objective with the same tool name and, when both sides provide an order ID, the same order. It marks that item completed, stores the actual fingerprint, and emits progress through state consumed by the trace. Failed calls, rejected confirmations, and read calls do not advance the plan.

After completion, runtime hands the order lock to the next pending objective when that objective has an `order_id`. If its order is unknown, runtime clears the lock so the planner can perform the reads needed to resolve it. This makes the lock current-objective scoped instead of permanently tied to the most recent write.

When identical write tools appear more than once, first-pending matching preserves their declared order. Different argument sets remain independently protected by their action fingerprints.

If no plan exists or no entry matches a successful write, existing ledger behavior remains unchanged. The completed write is still recorded, but runtime does not fabricate a plan item after the fact.

## Continuation

`confirm_pending_and_continue` stops constructing a free-form “completed write” instruction as its primary state carrier. It resumes with the original objective and a short directive to follow `NEXT_WRITE_OBJECTIVE`; authoritative completion data comes from the ledger.

The locked-order rule remains active while the current pending objective targets that order. E16 will not add automatic cross-order write rewriting. Reads may follow a later objective only after the current objective is complete and the lock has been handed off or cleared; until then, the current locked-order protection applies.

## Safety Boundaries

- Benchmark task IDs and expected actions never enter planner or runtime state.
- Planned tool names must exist and be write tools.
- Plan status supplied by an LLM is ignored; all accepted items start as `pending`.
- Write arguments are never generated or rewritten by the plan subsystem.
- Every write still requires exact fingerprint confirmation.
- A tool error, customer rejection, or missing pending action leaves the plan unchanged.
- The order lock changes only after a successful write advances the current plan item.
- Plan size is capped to prevent context growth.

## Testing

Unit tests cover:

- accepting and normalizing a valid multi-write plan;
- rejecting unknown and read-only planned tools;
- preserving duplicate write-tool objectives in order;
- advancing exactly one matching item after successful execution;
- not advancing on tool failure or confirmation rejection;
- exposing the next pending objective in planner context;
- preserving existing behavior when no plan is present;
- retaining write arguments and Guard confirmation semantics unchanged.

The full backend suite and saved E9-E15 artifact gates must remain green.

## Real Regression

Use tau2 Retail task `59` only as an external acceptance fixture. It combines `cancel_pending_order` with `modify_pending_order_address`, unlike E15 tasks `71` and `96`, which both combine address and item modification.

Acceptance requires:

- both expected writes proposed with exact arguments;
- each write independently confirmed;
- both successful executions reflected in the database state;
- no task-ID branch in production code;
- estimated list cost no greater than `CNY 0.05` for the task.

After task `59` passes, rerun the saved E15 gate locally. A paid rerun of tasks `71` and `96` is not required unless local tests reveal a regression that saved artifacts cannot assess.

## Deliverables

- structured write-plan state and parser contract;
- runtime plan validation and progression;
- compact next-objective planner context;
- unit and integration coverage;
- task `59` runtime artifact and Markdown report;
- E16 offline quality gate;
- README and roadmap status update.

## Deferred Work

- Parallel writes and automatic reordering.
- Cross-order lock release policies beyond sequential declared objectives.
- User editing of the plan in the frontend.
- Synthetic benchmark cases not present in tau2 Retail.
