# Customer Service Business Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 打通客服写操作从确认到结果与连续操作的完整闭环。

**Architecture:** 复用现有 Guard、Objective Ledger、MCP 和 SQLite，增强 `SupportService.confirm_action` 的结果投影和后续动作持久化。前端继续消费现有 block 协议，无需按工具硬编码流程。

**Tech Stack:** Python 3.12、FastAPI、SQLite、Pydantic、pytest、原生 JavaScript

**Spec:** `docs/superpowers/specs/2026-10-24-customer-service-business-closure-design.md`

## Global Constraints

- 每个写操作必须独立确认。
- 不得重复执行已领取动作。
- 只有真实执行成功才能返回 succeeded。
- 不增加新的模型调用。

## Review Focus

- 第一项成功但第二项待确认时不能宣称整个目标完成。
- 工具执行返回 error 时不能落 succeeded。
- 重复确认不能创建重复后续动作。
- 恢复后的会话必须保留下一确认卡。
- 人工接管与确认之间的竞争继续由 compare-and-set 阻止。

---

### Task 1: 具体操作结果

**Files:** `backend/app/support/service.py`, `backend/tests/support/test_support_service.py`

- [x] 写取消成功与执行失败的失败测试。
- [x] 实现客户可读结果和结构化证据。
- [x] 运行定向测试。

### Task 2: 连续操作续接

**Files:** `backend/app/support/service.py`, `backend/tests/support/test_support_service.py`

- [x] 写确认后出现下一确认卡的失败测试。
- [x] 持久化下一 PendingAction 并返回新 action id。
- [x] 验证第二次确认完成且无重复执行。

### Task 3: API 与完整回归

**Files:** `backend/tests/api/test_support_api.py`, `backend/tests/e2e/test_support_product_flow.py`

- [x] 固定 API block 契约与端到端闭环。
- [x] 运行客服链路与完整后端测试。
- [x] 重启本地服务并验证健康状态。
