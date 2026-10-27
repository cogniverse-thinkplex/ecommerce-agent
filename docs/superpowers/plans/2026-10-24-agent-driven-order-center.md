# Agent Driven Order Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为登录客户提供安全的订单查询中心，并用同源嵌入的现有客服完成上下文售后任务。

**Architecture:** `OrderCenterService` 通过现有 MCP RetailToolPort 读取本人订单并输出显式 DTO；订单 API 不暴露任何写操作。订单页创建并绑定受服务端验证的客服会话，通过嵌入模式复用现有 SSE、Guard、确认卡和人工接管。

**Tech Stack:** FastAPI、Pydantic、tau2 Retail MCP、原生 HTML/CSS/JS、pytest、浏览器验收。

**Spec:** `docs/superpowers/specs/2026-10-23-agent-driven-order-center-design.md`

## Global Constraints

- 客户端不得提交或选择 `user_id`。
- 非本人订单与不存在订单统一返回 404。
- 订单中心不得提供直接写 API；所有修改继续经过 Agent Guard。
- 嵌入客服必须复用现有会话和流式协议。

## Review Focus

- MCP 单个订单失败时列表保持可用且不泄露错误。
- 上下文绑定同时校验会话所有权和订单所有权。
- 开发人员与未登录访问按现有角色门禁处理。
- 移动端助手不遮挡订单内容或产生横向滚动。
- 金额、退款、取消订单口径与消费分析一致。

---

### Task 1: Order query domain and API

**Files:** Create `backend/app/orders/models.py`, `backend/app/orders/service.py`, `backend/app/api/orders.py`; modify `backend/app/auth/service.py`, `backend/app/api/main.py`; test `backend/tests/orders/test_service.py`, `backend/tests/api/test_orders_api.py`.

- [x] 先添加服务与 API 失败测试，覆盖归属、筛选、金额、部分失败和认证。
- [x] 实现显式订单 DTO、只读服务、路由与 `/orders` 静态门禁。
- [x] 运行订单定向测试。

### Task 2: Trusted order context

**Files:** Modify `backend/app/agent/session_service.py`, `backend/app/support/service.py`, `backend/app/api/orders.py`; test `backend/tests/orders/test_order_context.py`.

- [x] 先添加会话和订单双重归属测试以及审计事件断言。
- [x] 实现创建/复用会话并设置 `active_order_id`，只接受服务端验证结果。
- [x] 证明后续写工具仍产生 pending confirmation。

### Task 3: Order center UI and embedded assistant

**Files:** Create `backend/app/static/orders/index.html`, `orders.css`, `orders.js`; modify support HTML/CSS/JS and customer navigation; test static pages.

- [x] 先添加页面结构、无直接写端点和嵌入模式契约测试。
- [x] 实现列表、筛选、详情、失败/空状态、助手面板和移动端抽屉。
- [x] 支持客服页按 URL 加载服务端创建的会话和预填问题。

### Task 4: Verification

**Files:** Create `scripts/validate_orders_ui.mjs`; update README.

- [x] 验证真实登录、本人订单、上下文助手和跨账户 404。
- [x] 完成窄屏浏览器和响应式断点检查（当前 IAB 662px；390px 由同一 `max-width:720px` CSS contract 覆盖）。
- [x] 运行完整测试套件和本地产品验收。
