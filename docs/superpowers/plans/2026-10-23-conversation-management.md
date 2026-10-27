# 客服会话管理实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为客服中心增加逻辑删除、空会话清理、置顶、重命名和单一文件夹式分组。

**Architecture:** 使用 SQLite migration 扩展会话元数据并新增所有者隔离的分组表；SupportService 负责空会话清理和管理规则，FastAPI 暴露客户安全 API，现有原生 JavaScript 侧栏提供分组和会话菜单。

**Tech Stack:** Python 3.12、FastAPI、Pydantic、SQLite、原生 ES Modules、pytest。

**Spec:** `docs/superpowers/specs/2026-10-23-conversation-management-design.md`

## Global Constraints

- 删除业务会话必须逻辑归档，不能物理删除消息、确认、工具审计或人工工单。
- 每个会话最多属于一个分组，删除分组时会话回到未分组。
- 所有客户 API 必须按登录用户校验会话和分组所有权。
- 0 个用户问题的旧空会话在创建新会话时自动归档。
- 不改变 Agent、MCP、订单数据和写操作确认策略。

## Review Focus

- 用户提交其他用户的会话或分组 ID时必须返回 404，不能泄漏存在性。
- 删除包含会话的分组时会话必须保留并变为未分组。
- 连续点击新建会话不能累积多个 0 问题活动会话。
- 用户重命名后，后续消息不能重新覆盖标题。
- 置顶排序在分组内稳定，并以最后提问时间作为普通排序依据。

---

### Task 1: SQLite 会话管理模型

**Files:**
- Create: `backend/app/persistence/migrations/008_conversation_management.sql`
- Modify: `backend/app/persistence/models.py`
- Modify: `backend/app/persistence/sqlite.py`
- Test: `backend/tests/persistence/test_conversation_management_repository.py`

**Interfaces:**
- Produces: `ConversationGroupRecord`；会话仓储的 `update_management`、`archive_empty_for_owner`；分组仓储 CRUD。

- [ ] 先写仓储失败测试，覆盖迁移、所有者过滤、置顶字段、分组删除回到未分组和空会话归档。
- [ ] 运行测试并确认因 schema/API 缺失而失败。
- [ ] 实现 migration、Pydantic 模型和 SQLite 仓储。
- [ ] 运行仓储测试并确认通过。

### Task 2: 服务与客户 API

**Files:**
- Modify: `backend/app/support/models.py`
- Modify: `backend/app/support/service.py`
- Modify: `backend/app/api/support.py`
- Test: `backend/tests/api/test_support_api.py`

**Interfaces:**
- Consumes: Task 1 的会话与分组仓储。
- Produces: `PATCH /conversations/{id}` 和 conversation-groups CRUD；扩展后的安全会话摘要。

- [ ] 写失败测试，覆盖重命名、置顶排序、移动分组、逻辑删除、所有者隔离和创建新会话时清理旧空会话。
- [ ] 运行测试并确认失败原因匹配缺失接口。
- [ ] 实现服务规则、请求模型和 API。
- [ ] 运行 API 测试并确认通过。

### Task 3: 客服侧栏交互

**Files:**
- Modify: `backend/app/static/support/index.html`
- Modify: `backend/app/static/support/history.js`
- Modify: `backend/app/static/support/api.js`
- Modify: `backend/app/static/support/app.js`
- Modify: `backend/app/static/support/styles.css`
- Test: `backend/tests/api/test_support_static.py`

**Interfaces:**
- Consumes: Task 2 的会话管理与分组 API。
- Produces: 分组侧栏、会话菜单、重命名/置顶/移动/删除和分组管理交互。

- [ ] 写静态前端失败测试，锁定按钮、菜单、分组操作和确认文案。
- [ ] 运行测试并确认失败。
- [ ] 实现语义化侧栏交互和响应式样式，更新缓存版本。
- [ ] 运行静态与 API 测试并确认通过。

### Task 4: 文档与完整验收

**Files:**
- Modify: `README.md`
- Modify: `docs/final_implementation_roadmap.md`
- Modify: `scripts/validate_support_ui.mjs`

**Interfaces:**
- Consumes: Tasks 1-3 的最终公共行为。

- [ ] 更新验收脚本，覆盖分组创建、会话重命名/置顶/移动、逻辑删除和空会话清理。
- [ ] 更新 README 与路线图的数据口径。
- [ ] 运行完整后端测试、前端验收、产品栈验收和 8020 健康检查。
- [ ] 重启 8020 并保持服务在线。
