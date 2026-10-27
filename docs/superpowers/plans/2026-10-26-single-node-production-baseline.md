# Single-node Production Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a test-backed single-node production baseline with fail-fast configuration, operational probes, safe request telemetry, recoverable SQLite data, and hardened container operations.

**Architecture:** Keep the existing FastAPI/SQLite/MCP topology and add narrow operations modules around it. Production-only constraints are activated by `ECOM_ENV=production`; application probes and middleware remain dependency-injectable for tests; backup tooling uses Python's SQLite API rather than copying a live file.

**Tech Stack:** Python 3.12, FastAPI, SQLite, pytest, Docker Compose

**Spec:** `docs/superpowers/specs/2026-10-26-single-node-production-baseline-design.md`

## Global Constraints

- Do not expose or commit API keys, cookies, request bodies, or customer data.
- Preserve local development behavior unless `ECOM_ENV=production`.
- Keep SQLite single-node deployment; PostgreSQL/Redis/multi-replica are deferred.
- Every implementation task follows RED-GREEN TDD and ends with executable verification.

## Review Focus

- Invalid or malicious incoming request IDs must never be reflected into logs or headers unchanged.
- A tool backend outage must make readiness fail without making liveness fail.
- Production validation errors must identify missing variables without printing their values.
- Backing up a WAL-mode database during writes must produce an integrity-valid snapshot.
- Restore must not overwrite an existing target without explicit operator intent.

---

### Task 1: Production configuration gate

**Files:** Create `backend/app/operations/config.py`; modify `backend/app/api/main.py`; test `backend/tests/operations/test_production_config.py`.

**Interfaces:** Produces `validate_runtime_config(environ: Mapping[str, str]) -> None` and `ProductionConfigError`.

- [x] Write tests for local bypass, complete production configuration, every required production invariant, and secret-safe error text.
- [x] Run the focused tests and observe failure because the operations module does not exist.
- [x] Implement validation and call it before default application services are constructed.
- [x] Run the focused tests to green.

### Task 2: Health, security headers, and request telemetry

**Files:** Create `backend/app/operations/health.py`, `backend/app/operations/http.py`; modify `backend/app/api/main.py`; test `backend/tests/api/test_operational_api.py`.

**Interfaces:** Produces `ReadinessChecker.check()`, `normalize_request_id()`, security-header and structured-log helpers.

- [x] Write API tests for liveness/readiness separation, dependency failure, request-ID normalization, security headers, and sanitized JSON request logs.
- [x] Run focused tests and observe the expected missing behavior.
- [x] Implement the checker, `/ready`, and a single outer operations middleware that applies to public and protected responses.
- [x] Run the focused tests to green.

### Task 3: SQLite backup and restore

**Files:** Create `backend/app/operations/sqlite_backup.py`, `scripts/backup_sqlite.py`, `scripts/restore_sqlite.py`; test `backend/tests/operations/test_sqlite_backup.py`.

**Interfaces:** Produces `create_backup(source, destination_dir, retain) -> BackupResult` and `restore_backup(source, target, replace) -> RestoreResult`.

- [x] Write tests for valid backup/restore, metadata/hash, corrupt source rejection, retention, and overwrite protection.
- [x] Run focused tests and observe failure because functions do not exist.
- [x] Implement online backup, integrity checking, atomic publish, retention and guarded restore; add CLI wrappers.
- [x] Run the focused tests and a CLI round trip to green.

### Task 4: Hardened deployment and runbook

**Files:** Create `docker-compose.production.yml`, `.env.production.example`, `docs/operations/production-runbook.md`; modify `docker-compose.yml`, `README.md`, `backend/tests/ops/test_runtime_configuration.py`.

**Interfaces:** Operators use Compose with a production overlay and documented backup/restore/rollback procedures.

- [x] Extend static configuration tests for readiness healthcheck, restart policy, resource/log limits, read-only filesystems, secrets-free template, and runbook commands.
- [x] Run focused tests and observe failure against current deployment files.
- [x] Add the production overlay, environment template, Compose readiness wiring, and runbook; link from README.
- [x] Run ops tests and the complete backend suite. Compose parsing is documented for the target host; this workstation does not have the Docker CLI installed.

