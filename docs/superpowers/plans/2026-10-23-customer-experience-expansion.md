# 客户体验扩展实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付多地址簿、A+B 客服界面和个人消费分析三个可完整使用的客户功能。

**Architecture:** SQLite 保存地址簿和演示订单日期扩展，tau2-retail 继续作为订单与默认地址事实源。FastAPI 提供当前用户专属 API，原生 ES Modules 页面负责交互和可视化。

**Tech Stack:** Python、FastAPI、Pydantic、SQLite、HTML、CSS、原生 JavaScript、pytest。

**Specs:** `docs/superpowers/specs/2026-10-23-customer-address-book-design.md`；`docs/superpowers/specs/2026-10-23-customer-shell-spending-design.md`

## Global Constraints

- 客户只能读取和修改自己的地址、订单与消费统计。
- 默认地址同步 tau2 失败时不得提交本地默认状态。
- 演示订单日期固定可复现，并在页面明确标注。
- 不引入新的前端框架或图表依赖。
- 桌面与移动端均不可出现文本重叠或横向溢出。

## Review Focus

- 删除默认地址时必须拒绝，并给出可操作提示。
- tau2 默认地址同步失败必须保持原默认地址。
- 退款和取消订单不能抬高净消费。
- 未知商品必须进入“其他”类别。
- 无订单客户必须看到零值空状态而不是页面错误。

---

### Task 1: 多地址簿持久化与业务规则

**Files:**
- Create: `backend/app/persistence/migrations/012_customer_addresses.sql`
- Modify: `backend/app/persistence/models.py`
- Modify: `backend/app/persistence/sqlite.py`
- Create: `backend/app/account/address_service.py`
- Test: `backend/tests/persistence/test_customer_address_repository.py`
- Test: `backend/tests/account/test_address_service.py`

**Interfaces:**
- Produces: `CustomerAddressRecord`、`SqliteCustomerAddressRepository` 和 `CustomerAddressService` 的 list/create/get/update/archive/set_default 方法。

- [x] 先写迁移、所有权、默认唯一性、逻辑删除和同步失败回滚测试并确认失败。
- [x] 实现地址记录、仓储及服务；首次列表为空时导入 tau2 默认地址。
- [x] 运行地址持久化与服务测试并确认通过。

### Task 2: 地址簿 API 与页面

**Files:**
- Modify: `backend/app/api/auth.py`
- Modify: `backend/app/api/main.py`
- Modify: `backend/app/static/account/index.html`
- Modify: `backend/app/static/account/account.js`
- Modify: `backend/app/static/account/account.css`
- Create: `backend/app/static/account/address/index.html`
- Create: `backend/app/static/account/address/address.js`
- Create: `backend/app/static/account/address/address.css`
- Test: `backend/tests/api/test_auth_api.py`
- Test: `backend/tests/api/test_auth_static.py`

**Interfaces:**
- Consumes: Task 1 `CustomerAddressService`。
- Produces: `/api/v1/auth/addresses` CRUD/default API 与 `/account/address/` 编辑页。

- [x] 先写 API 所有权、验证、默认删除保护和静态页面测试并确认失败。
- [x] 实现地址 API、账户地址卡片列表及独立新增/编辑页面。
- [x] 运行认证 API 与静态测试并确认通过。

### Task 3: 演示订单时间与消费统计服务

**Files:**
- Create: `backend/app/persistence/migrations/013_demo_order_metadata.sql`
- Create: `backend/app/account/spending.py`
- Create: `backend/app/demo/seed_order_history.py`
- Modify: `backend/app/persistence/sqlite.py`
- Test: `backend/tests/account/test_spending.py`
- Test: `backend/tests/demo/test_seed_order_history.py`

**Interfaces:**
- Produces: `SpendingService.summary(actor, period)`，返回 summary、series、categories、recent_orders 和 demo_data 标志。

- [x] 先写稳定日期、周期聚合、退款净额、分类分摊守恒、未知分类和空数据测试并确认失败。
- [x] 实现元数据仓储、固定历史生成、类别映射和统计服务。
- [x] 运行消费统计单元测试并确认通过。

### Task 4: 消费分析 API 与页面

**Files:**
- Modify: `backend/app/api/auth.py`
- Modify: `backend/app/api/main.py`
- Create: `backend/app/static/account/spending/index.html`
- Create: `backend/app/static/account/spending/spending.js`
- Create: `backend/app/static/account/spending/spending.css`
- Test: `backend/tests/api/test_auth_api.py`
- Test: `backend/tests/api/test_auth_static.py`

**Interfaces:**
- Consumes: Task 3 `SpendingService.summary`。
- Produces: `/api/v1/auth/spending?period=` 与 `/account/spending/`。

- [x] 先写周期验证、用户隔离、零值响应、页面控件和可视化静态测试并确认失败。
- [x] 实现消费统计 API、周期控件、指标、趋势、类别排行及订单表。
- [x] 运行认证 API 与静态测试并确认通过。

### Task 5: A+B 客服界面重构

**Files:**
- Modify: `backend/app/static/support/index.html`
- Modify: `backend/app/static/support/app.js`
- Modify: `backend/app/static/support/styles.css`
- Test: `backend/tests/api/test_support_static.py`

**Interfaces:**
- Consumes: 现有 `/api/v1/auth/me` 与 Task 4 消费分析页面地址。
- Produces: 用户身份侧栏入口、消费分析导航和精简聊天顶栏。

- [x] 先写用户姓名/编辑标志、旧口号删除、消费入口和响应式结构测试并确认失败。
- [x] 实现 A+B 布局、身份入口和视觉系统，保留全部现有会话与人工服务功能。
- [x] 运行客服静态测试并确认通过。

### Task 6: 完整验收

**Files:**
- Modify: `README.md`

- [x] 运行 JavaScript 语法检查和完整后端测试，预期零失败。
- [x] 重启 8020，运行产品栈验收。
- [x] 浏览器检查客服中心、地址列表/编辑、消费周/月/年与移动端布局。
- [x] 更新 README 的客户功能、数据口径和演示数据说明。
