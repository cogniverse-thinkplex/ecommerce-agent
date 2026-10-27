# 用户反馈与运行问题可观测系统实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为已登录客服用户提供会话反馈入口，并为开发人员提供可检索、可聚合、可处理的反馈中心和运行问题中心，同时整理 Dashboard 的全局运行环境展示。

**Architecture:** 在现有 SQLite Unit of Work 中增加反馈与问题仓储，以独立 `ObservabilityService` 承担权限校验、脱敏、错误聚合和概览指标。FastAPI、Agent runtime、工具适配器和客服前端通过窄接口上报问题，Dashboard 通过开发人员专用 API 展示和处理反馈及问题；采集失败始终旁路，不改变原业务结果。

**Tech Stack:** Python 3.12、FastAPI、Pydantic、SQLite、原生 HTML/CSS/JavaScript、pytest、现有浏览器验证脚本。

**Spec:** `docs/superpowers/specs/2026-10-21-feedback-runtime-observability-design.md`

## Global Constraints

- 只允许已登录普通用户为归属于自己的客服会话提交反馈，不开放匿名反馈。
- 普通用户 API 永不返回 `developer_note` 或 `resolved_by_user_id`。
- 错误记录不得包含密码、Cookie、会话令牌、API Key、完整地址、支付字段或原始自由文本工具参数。
- 预期认证结果、输入校验、资源不存在、待确认、用户拒绝和业务规则拒绝不得记录为运行问题。
- 问题采集失败只写本地标准日志，不能覆盖原始业务响应或中断客服流程。
- 不新增外部 SaaS、消息通知、附件、多租户或自动修复依赖。
- Dashboard 标题下不再重复显示 Planner 长文本；完整运行配置只在侧栏环境区和概览按需展示。
- 新增界面必须在 1440x900 和 390x844 下无横向溢出。
- 当前目录未检测到 Git 元数据；每个任务以测试绿灯和 ledger 记录作为检查点，不执行不可用的提交步骤。

## Review Focus

- 并发或快速重复的同指纹错误：必须只保留一个问题行并正确增加 `occurrence_count`；Task 2 的仓储聚合测试覆盖。
- 反馈引用不属于当前用户的会话或消息：必须返回 404/权限安全错误且不泄露存在性；Task 2 和 Task 3 的服务/API 测试覆盖。
- 错误上下文嵌套对象、大小写键名和超长字符串：必须递归脱敏和截断；Task 2 的脱敏参数化测试覆盖。
- 问题采集数据库自身异常：原始 API/Agent/工具错误仍按原契约返回；Task 3 的故障注入测试覆盖。
- 概览某一来源不可用或没有历史评测：其他指标仍可显示，失败项为 `unavailable` 而不是伪装为零；Task 3 和 Task 5 的测试覆盖。

---

### Task 1: 数据库迁移与持久化契约

**Files:**
- Create: `backend/app/persistence/migrations/003_feedback_runtime_issues.sql`
- Modify: `backend/app/persistence/models.py`
- Modify: `backend/app/persistence/repositories.py`
- Modify: `backend/app/persistence/sqlite.py`
- Test: `backend/tests/persistence/test_observability_repositories.py`

**Interfaces:**
- Consumes: 现有数字顺序迁移加载器、`SqliteUnitOfWork`、`utc_now()`。
- Produces: `FeedbackRecord`、`RuntimeIssueRecord`；`FeedbackRepository` 和 `RuntimeIssueRepository` 协议；`SqliteUnitOfWork.feedback`、`SqliteUnitOfWork.runtime_issues`。

- [ ] **Step 1: 写迁移与模型失败测试**

在 `test_observability_repositories.py` 中新增 `test_migration_creates_feedback_and_runtime_issue_tables`，断言新 Unit of Work 暴露两个仓储，反馈外键和 spec 中所有枚举约束生效，关闭后重新连接仍可读取记录。

- [ ] **Step 2: 运行测试并确认因表和接口缺失失败**

Run: `./scripts/test_backend.sh backend/tests/persistence/test_observability_repositories.py -q`
Expected: FAIL，错误指向 `feedback`/`runtime_issues` 仓储或表不存在。

- [ ] **Step 3: 实现迁移与 Pydantic 记录模型**

实现 spec 第 4 节全部列、检查约束与索引。定义：

```python
class FeedbackRecord(BaseModel): ...
class RuntimeIssueRecord(BaseModel): ...
```

枚举字面量名称严格使用 spec 值，时间字段使用 timezone-aware `datetime`。

- [ ] **Step 4: 实现仓储协议与 SQLite 读写**

定义并实现：

```python
FeedbackRepository.append(record: FeedbackRecord) -> None
FeedbackRepository.get(feedback_id: str) -> FeedbackRecord | None
FeedbackRepository.list_for_conversation(conversation_id: str) -> list[FeedbackRecord]
FeedbackRepository.list_filtered(*, status: str | None, rating: str | None, category: str | None, query: str | None, limit: int, offset: int) -> tuple[list[FeedbackRecord], int]
FeedbackRepository.update_review(feedback_id: str, *, status: str, developer_note: str | None, resolved_by_user_id: str | None, updated_at: datetime) -> FeedbackRecord

RuntimeIssueRepository.upsert_occurrence(record: RuntimeIssueRecord) -> RuntimeIssueRecord
RuntimeIssueRepository.get(issue_id: str) -> RuntimeIssueRecord | None
RuntimeIssueRepository.list_filtered(*, status: str | None, severity: str | None, source: str | None, query: str | None, limit: int, offset: int) -> tuple[list[RuntimeIssueRecord], int]
RuntimeIssueRepository.update_review(issue_id: str, *, status: str, developer_note: str | None, resolved_by_user_id: str | None, resolved_at: datetime | None) -> RuntimeIssueRecord
```

- [ ] **Step 5: 扩充仓储行为测试并跑绿**

覆盖筛选、分页上限、处理状态更新、重启持久化、同指纹累加时保留 `first_seen_at` 并更新 `last_seen_at`。Run: `./scripts/test_backend.sh backend/tests/persistence/test_observability_repositories.py -q`；Expected: PASS。

### Task 2: 可观测领域服务、权限与脱敏

**Files:**
- Create: `backend/app/observability/__init__.py`
- Create: `backend/app/observability/models.py`
- Create: `backend/app/observability/redaction.py`
- Create: `backend/app/observability/service.py`
- Test: `backend/tests/observability/test_redaction.py`
- Test: `backend/tests/observability/test_service.py`

**Interfaces:**
- Consumes: Task 1 的仓储与记录模型、`AuthenticatedUser`、现有 conversation/message 仓储。
- Produces: `ObservabilityService`；`FeedbackCreate`、`FeedbackPublic`、`FeedbackDeveloperView`、`IssueDeveloperView`、`ObservabilityOverview`；`capture_issue(...)` 旁路接口。

- [ ] **Step 1: 写递归脱敏失败测试**

参数化覆盖大小写敏感键、嵌套 dict/list、邮箱、电话、地址、授权头、token/API Key、自由文本工具参数和超长摘要；断言非敏感的模块、工具名、HTTP 状态和错误码保留。

- [ ] **Step 2: 实现 `sanitize_context(value: Any, *, max_string_length: int = 500) -> Any`**

使用结构化递归处理，所有敏感键替换为 `[REDACTED]`，自由文本参数替换而非仅截断；不对任意对象调用危险的自定义序列化。

- [ ] **Step 3: 运行脱敏测试至通过**

Run: `./scripts/test_backend.sh backend/tests/observability/test_redaction.py -q`；Expected: PASS。

- [ ] **Step 4: 写服务失败测试**

覆盖：本人会话反馈成功；他人会话和不属于会话的 message 均用同一安全 NotFound 错误；普通用户视图隐藏内部字段；开发人员筛选/更新；同指纹聚合；采集仓储异常仅记录日志；概览无评测时返回 `latest_evaluation_success_rate: null` 和状态 `unavailable`。

- [ ] **Step 5: 实现领域模型、指纹与服务**

定义：

```python
ObservabilityService.submit_feedback(actor: AuthenticatedUser, conversation_id: str, command: FeedbackCreate) -> FeedbackPublic
ObservabilityService.list_own_feedback(actor: AuthenticatedUser, conversation_id: str) -> list[FeedbackPublic]
ObservabilityService.list_feedback_for_developer(actor: AuthenticatedUser, filters: FeedbackFilters) -> FeedbackPage
ObservabilityService.review_feedback(actor: AuthenticatedUser, feedback_id: str, command: FeedbackReview) -> FeedbackDeveloperView
ObservabilityService.capture_issue(*, source: IssueSource, severity: IssueSeverity, error_code: str, exception: BaseException | None, request_id: str | None, conversation_id: str | None, context: Mapping[str, Any]) -> None
ObservabilityService.list_issues_for_developer(actor: AuthenticatedUser, filters: IssueFilters) -> IssuePage
ObservabilityService.review_issue(actor: AuthenticatedUser, issue_id: str, command: IssueReview) -> IssueDeveloperView
ObservabilityService.overview(actor: AuthenticatedUser) -> ObservabilityOverview
```

指纹输入严格为 source、error_code、exception type、规范化调用位置/工具名，使用 SHA-256。

- [ ] **Step 6: 运行服务测试和持久化回归**

Run: `./scripts/test_backend.sh backend/tests/observability backend/tests/persistence -q`；Expected: PASS。

### Task 3: API 与运行错误采集接入

**Files:**
- Create: `backend/app/api/observability.py`
- Modify: `backend/app/api/support.py`
- Modify: `backend/app/api/main.py`
- Modify: `backend/app/agent/nodes/planner_node.py`
- Modify: `backend/app/tools/mcp_retail_adapter.py`
- Modify: `backend/app/tools/tau_retail_adapter.py`
- Test: `backend/tests/api/test_observability_api.py`
- Test: `backend/tests/api/test_support_feedback_api.py`
- Test: `backend/tests/observability/test_capture_boundaries.py`

**Interfaces:**
- Consumes: Task 2 的 `ObservabilityService`、命令/响应模型和 `capture_issue`。
- Produces: spec 第 6 节 API；应用生命周期中的单例 `ObservabilityService`；API、Planner、tool/MCP/database 采集入口。

- [ ] **Step 1: 写客服反馈 API 权限失败测试**

断言未登录为 401、开发人员不能冒充客户提交、本人会话可提交/读取、他人会话统一为 404、安全响应不含内部备注、正文超限为 422。

- [ ] **Step 2: 实现客服反馈路由**

在现有 support router 增加：

```python
POST /api/v1/support/conversations/{conversation_id}/feedback
GET /api/v1/support/conversations/{conversation_id}/feedback
```

复用当前会话 Cookie 鉴权和 ownership 规则。

- [ ] **Step 3: 写开发人员 API 失败测试**

覆盖反馈/问题列表与详情、筛选、最大 100 条分页、状态更新、普通用户 403、client-errors 限制 critical 和堆栈/正文长度、overview 局部 unavailable。

- [ ] **Step 4: 实现 `create_observability_router(...) -> APIRouter` 并注册**

实现 spec 第 6.2、6.3 节路径，统一将领域 NotFound/Forbidden/Validation 异常映射为稳定中文错误对象。

- [ ] **Step 5: 写采集边界故障注入测试**

模拟 API 未处理异常、Planner 解析失败、MCP 超时、数据库错误和采集仓储自身异常；另断言 401/403/404/422、待确认、拒绝和业务规则失败不写 `runtime_issues`。

- [ ] **Step 6: 接入五类后端采集点**

FastAPI middleware 使用请求 ID；Planner、工具适配器只在异常边界调用服务；数据库异常由 API/service 边界归类，避免仓储层循环记录自身写失败。保留现有异常类型和用户响应。

- [ ] **Step 7: 运行 API、Agent 和工具回归**

Run: `./scripts/test_backend.sh backend/tests/api backend/tests/observability backend/tests/agent backend/tests/tools -q`；Expected: PASS。

### Task 4: 客服中心反馈体验与前端错误上报

**Files:**
- Modify: `backend/app/static/support/index.html`
- Modify: `backend/app/static/support/api.js`
- Modify: `backend/app/static/support/chat.js`
- Create: `backend/app/static/support/feedback.js`
- Modify: `backend/app/static/support/app.js`
- Modify: `backend/app/static/support/styles.css`
- Modify: `scripts/validate_support_ui.mjs`
- Test: `backend/tests/api/test_support_static.py`

**Interfaces:**
- Consumes: Task 3 的 support feedback API 和 `POST /api/v1/observability/client-errors`。
- Produces: 消息级和会话级反馈控件；`submitFeedback(...)`；安全的前端请求错误上报。

- [ ] **Step 1: 写静态契约和浏览器验证失败断言**

断言语义化“有帮助/没帮助”按钮、负面分类、可选文字、提交状态、字符上限、失败保留输入；浏览器脚本验证移动端控件不遮挡输入与确认操作。

- [ ] **Step 2: 实现 `feedback.js` 状态与渲染**

提供：

```javascript
mountMessageFeedback(container, {conversationId, messageId})
mountConversationFeedback(container, {conversationId})
submitFeedback(payload)
```

使用 DOM API 和 `textContent`，不拼接用户或服务端文本到 `innerHTML`。正面可直接提交；负面展开分类和评论；失败不清空。

- [ ] **Step 3: 接入对话消息与会话级入口**

只对已送达 Agent 回复展示消息反馈；会话反馈放在历史/结束区域，不进入写操作确认区。提交期间禁用当前控件，其他会话不受影响。

- [ ] **Step 4: 实现前端错误上报**

`api.js` 对非预期 5xx、网络失败和响应解析失败异步调用 client-errors；忽略 401/403/404/422、AbortError 和反馈上报自身失败；不得发送请求 body、Cookie、消息正文或完整 stack。

- [ ] **Step 5: 跑静态测试和客服浏览器验证**

Run: `./scripts/test_backend.sh backend/tests/api/test_support_static.py backend/tests/api/test_support_feedback_api.py -q`；Expected: PASS。随后在运行产品栈上执行 `node scripts/validate_support_ui.mjs`；Expected: desktop/mobile PASS。

### Task 5: Dashboard 运行环境、反馈中心、问题中心与总体验收

**Files:**
- Modify: `backend/app/static/dashboard/index.html`
- Modify: `backend/app/static/dashboard/app.js`
- Modify: `backend/app/static/dashboard/styles.css`
- Modify: `backend/tests/api/test_dashboard_static.py`
- Create: `scripts/validate_observability_ui.mjs`
- Modify: `README.md`

**Interfaces:**
- Consumes: Task 3 的开发人员 observability API、Task 4 产生的真实反馈和 client error 数据。
- Produces: `?view=feedback`、`?view=issues`；侧栏运行环境；概览观测指标；反馈/问题筛选、详情和状态处理界面。

- [ ] **Step 1: 写 Dashboard 静态契约失败测试**

断言标题下不含重复 Planner 状态段；导航与 view section 含 `feedback`、`issues`；侧栏有运行环境；概览有健康、问题、反馈和评测指标；所有列表有加载、空、错误状态。

- [ ] **Step 2: 重构全局配置展示**

保留 `loadAppConfig()`，将结果渲染到侧栏 `environment-summary` 和概览详情；顶部只显示页面标题和开发人员操作。策略正文使用 details 按需展开，不在窄屏撑宽页面。

- [ ] **Step 3: 实现反馈中心**

新增 `loadFeedback(filters)`、`renderFeedbackPage(page)`、`openFeedbackDetail(id)`、`reviewFeedback(id, command)`。界面包含四个指标、状态/评分/分类/时间筛选、分页、关联消息上下文和内部备注。

- [ ] **Step 4: 实现问题中心**

新增 `loadIssues(filters)`、`renderIssuePage(page)`、`openIssueDetail(id)`、`reviewIssue(id, command)`。按严重程度和最近时间展示，明确显示聚合次数、影响会话、脱敏上下文和处理状态。

- [ ] **Step 5: 升级概览并处理局部失败**

通过 `/api/v1/observability/overview` 填充可点击指标；单项 `unavailable` 显示“暂不可用”及重试，不显示误导性 0；快捷入口带查询参数进入对应筛选视图。

- [ ] **Step 6: 写并运行 Dashboard 浏览器验收**

`validate_observability_ui.mjs` 在 1440x900 和 390x844 验证十个导航模块、URL 前进后退、运行环境展开、反馈筛选/详情/处理、问题筛选/详情/处理、空/错误状态和无横向溢出。

- [ ] **Step 7: 更新 README 运维说明**

记录迁移、反馈流程、问题来源/严重程度/状态、脱敏保证、开发人员处理步骤和本地验证命令；明确问题中心不是外部告警系统。

- [ ] **Step 8: 运行全量验收**

Run: `./scripts/validate_local.sh`；Expected: 所有 pytest 与 E9-E17 离线门禁 PASS。启动产品栈后运行 `node scripts/validate_support_ui.mjs` 和 `node scripts/validate_observability_ui.mjs`；Expected: desktop/mobile PASS。最后人工验证一个用户反馈和一个合成错误在 SQLite 重启后仍存在、权限与脱敏正确。
