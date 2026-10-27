# E11 Expanded Regression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the Retail regression beyond the original five tasks, reduce repeated LLM context, expose usage in Dashboard, and run all local gates from one command.

**Architecture:** Keep the existing runtime artifact as the source of truth. Add an expanded manifest to the regression runner, compact redundant planner context while preserving tool results, extend the existing Dashboard renderer, and compose existing checks in one shell entrypoint.

**Tech Stack:** Python 3.12, pytest, FastAPI static Dashboard, vanilla JavaScript, Bash, tau2 Retail.

**Spec:** `docs/final_implementation_roadmap.md` section “阶段 E 第十一轮”.

## Global Constraints

- Never branch on benchmark task ids in planner behavior.
- Every write remains behind Guard confirmation.
- Missing provider usage or unsupported pricing displays as `N/A`.
- The base split contains only one payment-update task; report that limitation instead of duplicating it.

## Review Focus

- Expanded artifacts contain every manifest task exactly once.
- Context compaction retains the latest user request and distinct tool results needed for planning.
- Quality gates reject undersized artifacts even when their successful subset passes.
- Dashboard summaries distinguish tokens, estimated list cost, and provider-reported cost.
- Unified validation never triggers a paid LLM run.

---

### Task 1: Expanded regression manifest and gate

- [ ] Test and implement the nine-task manifest.
- [ ] Test and implement minimum artifact-size validation.

### Task 2: Compact LLM planner context

- [ ] Test preservation of latest user context and distinct tool results.
- [ ] Implement deterministic context and schema compaction.

### Task 3: Dashboard usage and unified validation

- [ ] Test and render aggregate and per-task usage with `N/A` semantics.
- [ ] Add a non-paid unified validation script.
- [ ] Run expanded rule regression, focused tests, full suite, and unified validation.
