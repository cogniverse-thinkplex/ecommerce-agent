# E9 Write Workflow Expansion

## Goal

Raise the representative Retail runtime regression from 2/5 to 5/5 confirmed
business outcomes without task-id-specific logic.

## Scope

1. Generalize customer identity parsing for name/ZIP and email.
2. Reuse user details and order history to locate pending orders.
3. Propose guarded writes for cancellation, shipping-address updates, and
   payment-method updates.
4. Keep every write behind the existing confirmation gate and verify the
   resulting Tau2 database mutation.
5. Run focused tests, the complete backend suite, and the five-scenario runtime
   regression before declaring the stage complete.

## Design

- Intent is derived from the user's language, never from a benchmark task ID.
- Explicit order IDs take priority; otherwise the planner walks the authenticated
  user's order list and inspects each order.
- Address updates copy the current order address and replace only fields stated
  by the user.
- Payment updates select an authenticated user's payment method by requested
  brand and never fabricate a payment-method ID.
- Cancellation uses only the reasons accepted by the Retail tool contract.

## Verification

- Unit tests for identity parsing, read sequencing, and exact write arguments.
- Representative rule regression must report 5/5 business successes and 5/5
  confirmed outcomes.
- Full backend test suite must pass.
