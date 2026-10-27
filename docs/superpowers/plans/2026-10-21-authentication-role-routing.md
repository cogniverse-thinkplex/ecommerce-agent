# Authentication and Role Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add persistent customer/developer authentication, role-aware routing, conversation ownership, and developer-account management inside the existing engineering Dashboard.

**Architecture:** Extend the existing SQLite repository boundary with users, hashed browser sessions, security audit events, and conversation ownership. Add an `AuthService` plus FastAPI authorization dependencies, protect existing product surfaces and APIs by role, then add three small authentication pages and a developer-management view to the existing Dashboard.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, stdlib `sqlite3`, `hashlib.scrypt`, HttpOnly cookies, vanilla HTML/CSS/JavaScript, pytest, FastAPI TestClient, browser automation.

**Spec:** `docs/superpowers/specs/2026-10-21-authentication-role-routing-design.md`

## Global Constraints

- The initial developer is stored by SQL migration as `admin@local.dev` with temporary password `Admin@123456`, role `developer`, and mandatory first-login password change.
- Store only versioned scrypt password encodings and SHA-256 session-token hashes; never store or log plaintext passwords or raw session tokens.
- Public registration always creates role `customer`; only an authenticated developer may create another developer.
- The existing `/dashboard/` remains the complete developer observation application and gains developer management rather than being replaced.
- `/support/` remains the customer-facing application; support conversations are ownership-scoped.
- Product login does not replace the retail agent's domain-specific identity verification.
- No product authentication bypass is enabled by default; explicit test construction may inject an authenticated principal.
- Existing benchmark/runtime behavior remains independent of browser authentication.
- The workspace has no `.git`, so each task uses RED/GREEN evidence and the SDD ledger instead of commits.

## Review Focus

- Normalized duplicate emails such as `User@Example.com` and ` user@example.com ` must conflict without revealing whether a password exists; Task 1 and Task 2 add these tests.
- Disabled, expired, or revoked sessions must never authorize a cached browser page or API request; Task 2 and Task 3 add these tests.
- A forged role, user ID, or redirect supplied by the browser must not affect server-selected authorization or routing; Task 3 and Task 4 add these tests.
- Two simultaneous developer status changes must not disable the last active developer or allow self-disable; Task 2 adds transaction tests.
- Existing unowned conversations and another customer's conversations must never appear in a customer's support index or detail route; Task 3 adds isolation tests.

---

### Task 1: Authentication Schema, Migration Runner, and Cryptographic Primitives

**Files:**
- Create: `backend/app/persistence/migrations/002_authentication.sql`
- Modify: `backend/app/persistence/models.py`
- Modify: `backend/app/persistence/repositories.py`
- Modify: `backend/app/persistence/sqlite.py`
- Create: `backend/app/auth/__init__.py`
- Create: `backend/app/auth/passwords.py`
- Test: `backend/tests/persistence/test_auth_repositories.py`
- Test: `backend/tests/auth/test_passwords.py`

**Interfaces:**
- Produces: `UserRecord`, `AuthSessionRecord`, `AuthAuditEventRecord`; `UserRepository`, `AuthSessionRepository`, `AuthAuditRepository`; `hash_password(password: str) -> str`; `verify_password(password: str, encoded: str) -> bool`; ordered migration discovery in `SqliteUnitOfWork.initialize()`.
- Consumes: existing `SqliteUnitOfWork.transaction()` and UTC model conventions.

- [ ] **Step 1: Write failing migration and repository tests**

Cover ordered/idempotent migrations `[1, 2]`, seeded developer fields, absence of plaintext password, normalized case-insensitive email uniqueness, user CRUD/status, session hash lookup/revocation/expiry persistence, audit append/list, owner-aware conversation queries, foreign keys, and rollback.

- [ ] **Step 2: Write failing password tests**

Assert versioned scrypt output does not contain the password, the same password receives different salts, correct/wrong verification, malformed hash rejection, constant public password-policy errors, and `Admin@123456` verifies against the migration seed.

- [ ] **Step 3: Run focused tests and verify RED**

Run: `scripts/test_backend.sh backend/tests/persistence/test_auth_repositories.py backend/tests/auth/test_passwords.py -v`

Expected: FAIL because auth models, repositories, migration 2, and password helpers do not exist.

- [ ] **Step 4: Implement models, repository protocols, and migration 2**

Add the exact tables and constraints from the spec, add nullable `owner_user_id` to conversations, and use a precomputed scrypt encoding for the seeded administrator. Extend `ConversationRecord` with `owner_user_id: str | None` and add `list_active_for_owner(owner_user_id)`, `get_for_owner(conversation_id, owner_user_id)`, and `archive_for_owner(conversation_id, owner_user_id)`.

- [ ] **Step 5: Generalize migration execution and implement SQLite repositories**

Discover `NNN_*.sql` in numeric order, execute each unapplied migration exactly once, and expose `unit.users`, `unit.auth_sessions`, and `unit.auth_audit_events`. Session persistence receives a hash, never a raw token.

- [ ] **Step 6: Implement password hashing and policy**

Use `hashlib.scrypt`, 16 random salt bytes, `hmac.compare_digest`, and a versioned parseable encoding. Export `validate_password(password: str) -> None` with the 12-character upper/lower/digit/symbol policy.

- [ ] **Step 7: Run focused and existing persistence tests**

Run: `scripts/test_backend.sh backend/tests/persistence backend/tests/auth/test_passwords.py -v`

Expected: all tests PASS and existing migration-1 data remains readable.

### Task 2: Authentication Service and Developer Administration

**Files:**
- Create: `backend/app/auth/models.py`
- Create: `backend/app/auth/service.py`
- Test: `backend/tests/auth/test_auth_service.py`
- Test: `backend/tests/auth/test_developer_administration.py`

**Interfaces:**
- Consumes: Task 1 repositories and password helpers.
- Produces: `AuthService.register_customer(...)`, `login(...)`, `authenticate(raw_token)`, `logout(raw_token)`, `change_password(...)`, `list_developers(actor)`, `create_developer(actor, ...)`, `set_developer_status(actor, user_id, status)`; `AuthenticatedUser`; `IssuedSession`; stable domain exceptions.

- [ ] **Step 1: Write failing account/session lifecycle tests**

Cover customer registration, normalized duplicate conflict, valid/invalid login, disabled login, raw token only in return value, token hash at rest, 12-hour expiry, logout, restart persistence, forced password change, old-session revocation, and replacement-session issuance.

- [ ] **Step 2: Write failing developer-administration tests**

Cover role enforcement, list/create developer, creator attribution, temporary-password policy, mandatory password change, duplicate email, self-disable rejection, last-active-developer protection, transactional session revocation on disable, and audit events with no sensitive values.

- [ ] **Step 3: Run focused tests and verify RED**

Run: `scripts/test_backend.sh backend/tests/auth/test_auth_service.py backend/tests/auth/test_developer_administration.py -v`

Expected: FAIL because `AuthService` does not exist.

- [ ] **Step 4: Implement service models, exceptions, and customer authentication**

Use server-generated UUIDs and `secrets.token_urlsafe(32)`. Normalize email in one service helper. Return generic credential failures and never expose `password_hash` or `token_hash` in public models.

- [ ] **Step 5: Implement password-change and developer administration transactions**

All account mutation plus audit writes occur inside `SqliteUnitOfWork.transaction()`. Count active developers inside the same immediate transaction before disabling; reject the current actor and the last active developer.

- [ ] **Step 6: Run focused auth tests**

Run: `scripts/test_backend.sh backend/tests/auth -v`

Expected: all tests PASS.

### Task 3: FastAPI Authentication, Role Guards, and Conversation Ownership

**Files:**
- Create: `backend/app/api/auth.py`
- Create: `backend/app/api/dependencies.py`
- Create: `backend/app/api/admin.py`
- Modify: `backend/app/api/main.py`
- Modify: `backend/app/api/support.py`
- Modify: `backend/app/support/service.py`
- Modify: `backend/app/support/models.py`
- Test: `backend/tests/api/test_auth_api.py`
- Test: `backend/tests/api/test_role_authorization.py`
- Test: `backend/tests/api/test_support_ownership.py`
- Modify: existing engineering API tests to use an explicit authenticated developer client fixture.

**Interfaces:**
- Consumes: Task 2 `AuthService` and `AuthenticatedUser`; Task 1 owner-aware repositories.
- Produces: `/api/v1/auth/*`; `/api/v1/admin/developers/*`; `get_current_user`, `require_developer`, `require_password_changed`; authenticated page routing; owner-aware support methods with `actor_user_id`.

- [ ] **Step 1: Write failing auth route tests**

Cover register/login/logout/me/change-password, HttpOnly/SameSite cookie flags, server-selected redirects, generic invalid credentials, malformed requests, disabled and expired sessions, cookie clearing, and `409 password_change_required`.

- [ ] **Step 2: Write failing role and ownership tests**

Assert unauthenticated engineering/support access is `401`, customers receive `403` for every engineering route, developers retain current Dashboard APIs, forged body/query roles are ignored, customers see only owned conversations, cross-user IDs return safe `404`, and legacy unowned conversations remain hidden from customers.

- [ ] **Step 3: Run focused tests and verify RED**

Run: `scripts/test_backend.sh backend/tests/api/test_auth_api.py backend/tests/api/test_role_authorization.py backend/tests/api/test_support_ownership.py -v`

Expected: FAIL because auth routers and authorization dependencies are absent.

- [ ] **Step 4: Implement auth/admin routers and cookie handling**

Create one `AuthService` per application. Cookie name is `ecom_session`; max age derives from `ECOM_AUTH_SESSION_HOURS`; `Secure` derives from `ECOM_AUTH_COOKIE_SECURE`. Convert domain exceptions to stable Chinese error objects without internal details.

- [ ] **Step 5: Protect engineering routes and page mounts**

Apply `require_developer` to all current engineering/evaluation/session/admin endpoints while leaving `/health` and auth endpoints public. Serve protected static pages through authorization-aware routes or middleware rather than an unguarded `StaticFiles` mount. Password-change-required users may access only auth/logout/change-password assets and endpoints.

- [ ] **Step 6: Add support ownership to service and router boundaries**

Every support conversation creation stores the current authenticated user. Every list/get/message/action/archive operation accepts the actor user ID and uses owner-aware repository reads before touching runtime state. Developers using support create developer-owned test conversations; no impersonation parameter is accepted.

- [ ] **Step 7: Migrate existing API tests to authenticated fixtures and run API suites**

Run: `scripts/test_backend.sh backend/tests/api backend/tests/support backend/tests/e2e -q`

Expected: all tests PASS, with authentication explicit in product API tests and runtime unit tests unchanged.

### Task 4: Login, Registration, Password Change, and Dashboard Developer Management UI

**Files:**
- Create: `backend/app/static/auth/login.html`
- Create: `backend/app/static/auth/register.html`
- Create: `backend/app/static/auth/change-password.html`
- Create: `backend/app/static/auth/auth.css`
- Create: `backend/app/static/auth/auth.js`
- Modify: `backend/app/static/support/index.html`
- Modify: `backend/app/static/support/app.js`
- Modify: `backend/app/static/support/api.js`
- Modify: `backend/app/static/dashboard/index.html`
- Modify: `backend/app/static/dashboard/app.js`
- Modify: `backend/app/static/dashboard/styles.css`
- Test: `backend/tests/api/test_auth_static.py`
- Modify: `backend/tests/api/test_dashboard_static.py`
- Modify: `backend/tests/api/test_support_static.py`

**Interfaces:**
- Consumes: Task 3 auth/admin endpoints and redirects.
- Produces: accessible Chinese `/login/`, `/register/`, `/change-password/`; user identity/logout controls; Dashboard `开发人员管理` view.

- [ ] **Step 1: Write failing static and UI-contract tests**

Assert semantic Chinese forms, labelled password controls, autocomplete attributes, no role selector on public registration, no token/local-storage code, safe text rendering, logout controls, preserved Dashboard observation navigation, developer-management view, disabled submit states, and responsive layout contracts.

- [ ] **Step 2: Run static tests and verify RED**

Run: `scripts/test_backend.sh backend/tests/api/test_auth_static.py backend/tests/api/test_dashboard_static.py backend/tests/api/test_support_static.py -v`

Expected: FAIL because auth pages and Dashboard management UI are absent.

- [ ] **Step 3: Build the shared authentication pages**

Use restrained Chinese product styling, native labelled controls, visible validation, server-provided `redirect_to`, and focus management. Registration has display name/email/password/confirmation only. Change-password explains the first-login requirement without displaying the temporary password.

- [ ] **Step 4: Add authenticated identity and logout to support**

Fetch `/api/v1/auth/me` on startup, render display name, and use the server logout endpoint. Preserve selected conversation storage only; never store identity credentials or tokens.

- [ ] **Step 5: Extend the existing Dashboard with developer management**

Add one navigation item and view within the existing application. Render current developer rows and status, create-developer form with a temporary password, enable/disable controls with safe confirmation, and refresh from the authoritative API. Keep all current observation views intact.

- [ ] **Step 6: Run focused static and API tests**

Run: `scripts/test_backend.sh backend/tests/api/test_auth_static.py backend/tests/api/test_dashboard_static.py backend/tests/api/test_support_static.py backend/tests/api/test_auth_api.py -q`

Expected: all tests PASS.

### Task 5: End-to-End Browser Validation, Operations, and Full Regression

**Files:**
- Create: `backend/tests/e2e/test_authenticated_product_flow.py`
- Modify: `scripts/validate_support_ui.mjs`
- Modify: `scripts/validate_product_stack.sh`
- Modify: `scripts/validate_local.sh`
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `docs/final_implementation_roadmap.md`
- Modify: `.superpowers/sdd/2026-10-20-standalone-customer-support-center/progress.md`

**Interfaces:**
- Consumes: Tasks 1-4 complete authentication product.
- Produces: repeatable authenticated acceptance gates and updated operating instructions.

- [ ] **Step 1: Write failing end-to-end recovery tests**

Cover customer register/login/create support conversation/restart/resume/logout, second-customer isolation, seeded developer forced change/login/Dashboard access/create developer, new developer forced change, disabled developer session revocation, and no password/token leakage from database/API/log projections.

- [ ] **Step 2: Run E2E tests and verify RED or integration gaps**

Run: `scripts/test_backend.sh backend/tests/e2e/test_authenticated_product_flow.py -v`

Expected: FAIL until all full-stack ownership and redirect behavior is connected.

- [ ] **Step 3: Repair only integration gaps in owning modules**

Do not add demonstration-only authentication paths or weaken role/ownership checks. Add regression tests beside every repaired module.

- [ ] **Step 4: Update startup validation and documentation**

Validate login page, initial password change, authenticated health/product paths, MCP backend, customer registration, and role redirects. Document initial credentials, mandatory password change, database tables, cookie settings, reset behavior, and the production-security gap.

- [ ] **Step 5: Run real desktop and mobile browser flows**

At 1440x900 and 390x844, verify login, customer registration, support use, logout, seeded developer password change, complete Dashboard observation navigation, developer creation, form focus/errors, no horizontal overflow, and persistence after reload. Keep the final developer Dashboard and customer support tabs available for inspection.

- [ ] **Step 6: Run complete verification**

Run: `scripts/test_backend.sh -q`

Run: `scripts/validate_local.sh`

Run against a running stack: `BASE_URL=http://127.0.0.1:8000 node scripts/validate_support_ui.mjs`

Expected: all tests, saved-artifact gates, authenticated stack checks, and browser flows PASS.

- [ ] **Step 7: Perform final security/acceptance review**

Review every spec acceptance criterion, search responses/static assets/logging code for password/hash/token leakage, confirm all engineering routes carry developer authorization, and record Docker/browser-runner environment limitations rather than claiming them complete.
