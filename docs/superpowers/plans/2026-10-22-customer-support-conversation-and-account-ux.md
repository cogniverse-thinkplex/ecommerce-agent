# Customer Support Conversation and Account UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace generic conversation metadata and inline ratings with useful conversation summaries, customer account editing, and a dedicated issue-feedback workflow.

**Architecture:** Keep SQLite as the source of truth and derive question counts and last-question timestamps from persisted user messages. Extend the existing auth and observability services instead of introducing a second account or feedback subsystem; serve focused static pages through the current FastAPI application.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, SQLite, vanilla JavaScript/CSS, pytest, Playwright validation scripts.

**Spec:** `docs/superpowers/specs/2026-10-22-customer-support-conversation-and-account-ux-design.md`

## Global Constraints

- Conversation titles are deterministic summaries of the first user question, at most 32 Unicode characters, with no LLM call.
- Question counts include only `messages.role = 'user'`.
- The displayed time is the latest user-question time in the browser's local timezone.
- Customer email is read-only and internal `retail_user_id` is never rendered.
- Feedback descriptions are required and contain 1 to 2000 characters.
- Account and feedback routes use the existing customer authentication and ownership boundary.

## Review Focus

- A first question containing repeated whitespace or more than 32 characters produces a stable, readable title.
- Assistant cards, confirmations, and operation results do not increase the question count or last-question time.
- A customer cannot associate feedback with another customer's conversation.
- Empty or whitespace-only display names and feedback descriptions return 422 without persisting changes.
- Mobile header and navigation remain usable with a long customer display name and long conversation title.

---

### Task 1: Conversation Summary Semantics

**Files:**
- Modify: `backend/app/persistence/sqlite.py`
- Modify: `backend/app/support/models.py`
- Modify: `backend/app/support/service.py`
- Modify: `backend/app/static/support/history.js`
- Test: `backend/tests/support/test_support_service.py`
- Test: `backend/tests/api/test_support_api.py`

**Interfaces:**
- Produces: `SupportConversation.last_question_at: datetime | None`, repository methods for first/last/count user messages, and `summarize_question(text: str) -> str`.
- Consumes: existing `MessageRecord`, `ConversationRecord`, and support conversation APIs.

- [ ] Write failing tests proving a first question changes the title, only user messages count, a second question updates `last_question_at`, and long/whitespace-heavy text is summarized to at most 32 characters.
- [ ] Run `./scripts/test_backend.sh -q backend/tests/support/test_support_service.py backend/tests/api/test_support_api.py` and confirm the new assertions fail for the old semantics.
- [ ] Implement repository aggregate queries and update `SupportService.submit_message` and `_summary` with the exact interfaces above; persist title and `updated_at` in the same transaction as the first user message.
- [ ] Update `history.js` to render title, `N 个问题`, and localized `last_question_at`, using “尚未提问” when null.
- [ ] Run the focused tests and confirm they pass.

### Task 2: Customer Account Editing

**Files:**
- Modify: `backend/app/auth/service.py`
- Modify: `backend/app/api/auth.py`
- Modify: `backend/app/api/main.py`
- Create: `backend/app/static/account/index.html`
- Create: `backend/app/static/account/account.js`
- Create: `backend/app/static/account/account.css`
- Test: `backend/tests/auth/test_auth_service.py`
- Test: `backend/tests/api/test_auth_api.py`

**Interfaces:**
- Produces: `AuthService.update_profile(actor, *, display_name: str) -> AuthenticatedUser` and `PATCH /api/v1/auth/me` with `{display_name}`.
- Consumes: existing `GET /api/v1/auth/me` and `POST /api/v1/auth/change-password`.

- [ ] Write failing service and API tests for updating the current customer's trimmed display name, rejecting blank names, leaving email and Retail identity unchanged, and denying unauthenticated access.
- [ ] Run the focused auth tests and confirm failure for the missing interface.
- [ ] Implement the service/API and mount `/account/` behind the existing customer route guard.
- [ ] Build the account page with editable display name, read-only email, purchase-account status, password-change form, back-to-support action, and safe error states.
- [ ] Run focused tests and verify both successful and invalid updates.

### Task 3: Dedicated Issue Feedback

**Files:**
- Modify: `backend/app/observability/models.py`
- Modify: `backend/app/observability/service.py`
- Modify: `backend/app/api/observability.py`
- Modify: `backend/app/api/main.py`
- Create: `backend/app/static/support/feedback/index.html`
- Create: `backend/app/static/support/feedback/feedback.js`
- Create: `backend/app/static/support/feedback/feedback.css`
- Test: `backend/tests/observability/test_service.py`
- Test: `backend/tests/api/test_observability_api.py`

**Interfaces:**
- Produces: customer issue feedback creation with required comment, optional owned `conversation_id`, and category including `interface`.
- Consumes: existing feedback repository and engineering-console feedback listing.

- [ ] Write failing tests for standalone feedback, owned conversation association, cross-account rejection, `interface` category, and blank/overlong descriptions.
- [ ] Run focused observability tests and confirm the new behavior fails.
- [ ] Extend the existing feedback request/service while persisting compatibility value `rating = 'not_helpful'` without exposing ratings in the customer UI.
- [ ] Build `/support/feedback/` with category, required description, optional owned-conversation selector, submission success state, and return-to-support action.
- [ ] Run focused tests and confirm the engineering feedback list still returns the new records.

### Task 4: Support Shell Integration and Acceptance

**Files:**
- Modify: `backend/app/static/support/index.html`
- Modify: `backend/app/static/support/app.js`
- Modify: `backend/app/static/support/styles.css`
- Modify: `scripts/validate_support_ui.mjs`
- Modify: `README.md`

**Interfaces:**
- Consumes: Tasks 1-3 APIs and pages.
- Produces: final customer navigation and responsive acceptance coverage.

- [ ] Remove the inline rating panel and Retail-authentication badge; make the displayed customer name link to `/account/` and add a clear `/support/feedback/` navigation entry.
- [ ] Update responsive CSS so long names and titles truncate without overlapping the mobile header or composer.
- [ ] Extend the UI validation script to assert title summary, question count, time label, account navigation, absence of rating/auth badges, profile update, and feedback submission.
- [ ] Run `./scripts/test_backend.sh -q` and require zero failures.
- [ ] Start the SQLite + MCP product stack and run `BASE_URL=http://127.0.0.1:8020 node scripts/validate_support_ui.mjs`; require all browser assertions to pass.
- [ ] Manually inspect desktop and mobile screenshots, update README routes and data definitions, and keep the final service running on port 8020.
