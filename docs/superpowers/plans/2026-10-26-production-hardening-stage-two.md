# Production Hardening Stage Two Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add proactive abuse protection, scheduled data protection, machine-readable operational alerts, redaction, security scanning, and one-command acceptance to the single-node deployment.

**Architecture:** Add focused operations modules with dependency-injectable clocks and probes, wire login protection at the API boundary, and run backups/checks as separate scripts or Compose services. Keep state local because the accepted deployment target remains one API process.

**Tech Stack:** Python 3.12, FastAPI, SQLite, pytest, Docker Compose, pip-audit, Bandit

**Spec:** `docs/superpowers/specs/2026-10-26-production-hardening-stage-two-design.md`

## Global Constraints

- Never persist or log raw passwords, session tokens, API keys, Cookie headers, or plaintext login identifiers in limiter state.
- Local tests remain deterministic through injected clocks and probes.
- Production scripts fail closed and return non-zero on missing required scanners or failed checks.
- Multi-replica behavior is explicitly unsupported until shared limiter/storage infrastructure exists.

## Review Focus

- Attackers must not bypass the login limiter by varying email case or supplying `X-Forwarded-For`.
- A successful login must clear prior failures without clearing another account/IP key.
- Backup service failures must be visible and must not publish partial files.
- Redaction must recurse without mutating caller-owned objects.
- Acceptance scripts must not echo environment secrets.

---

### Task 1: Login abuse protection and redaction

**Files:** Create `backend/app/operations/rate_limit.py`, `backend/app/operations/redaction.py`; modify `backend/app/api/auth.py`, `backend/app/api/main.py`; test `backend/tests/api/test_login_rate_limit.py`, `backend/tests/operations/test_redaction.py`.

- [x] Write and run failing tests for threshold, retry header, expiry, success reset, key hashing and recursive redaction.
- [x] Implement the limiter, API integration and redaction utilities.
- [x] Run focused tests to green.

### Task 2: Automated backups and operational alerts

**Files:** Create `backend/app/operations/operational_checks.py`, `scripts/backup_daemon.py`, `scripts/check_operations.py`; modify `docker-compose.production.yml`; test `backend/tests/operations/test_operational_checks.py`, `backend/tests/ops/test_runtime_configuration.py`.

- [x] Write and run failing tests for ready/unready, stale backup, disk threshold and one-shot backup behavior/configuration.
- [x] Implement checks, CLI wrappers and the isolated backup Compose service.
- [x] Run focused tests and a real one-shot backup check to green.

### Task 3: Security scan and one-command production acceptance

**Files:** Create `scripts/security_scan.sh`, `scripts/production_acceptance.sh`; modify `benchmarks/pyproject.toml`, `benchmarks/uv.lock`, `.env.production.example`, `docs/operations/production-runbook.md`, `README.md`; test `backend/tests/ops/test_production_stage_two.py`.

- [x] Write and run failing static contract tests for strict scanner and acceptance steps.
- [x] Add pip-audit/Bandit tooling, secret-pattern checks, acceptance orchestration and documentation.
- [x] Run security tooling and the complete backend suite. The local acceptance flow is verified component-by-component because this workstation has no Docker CLI; the target-host command is documented.

