# 用户反馈与运行问题可观测系统设计

日期：2026-10-21

## 1. 目标

在现有本地电商 Agent 准产品中补齐可持续使用所需的两条闭环：

1. 已登录普通用户能够针对自己的客服会话提交满意度和文字反馈，开发人员能够在工程控制台检索、分类和处理反馈。
2. 系统能够统一收集 API、Planner、工具/MCP、数据库和前端请求过程中发生的非预期错误，按错误指纹聚合，并由开发人员跟踪处理状态。

同时整理 Dashboard 的全局信息架构：页面标题只表达当前模块；Planner、工具后端和策略状态不再重复占据每个页面顶部，而是进入侧栏底部的紧凑“运行环境”区域，并在概览页提供完整状态。

本阶段面向本地完整演示和使用，不接入外部 SaaS 可观测平台，不实现匿名反馈，不实现邮件、短信或工单系统通知。

## 2. 用户与权限

### 2.1 普通用户

- 必须登录后才能提交反馈。
- 只能为归属于自己的客服会话提交反馈。
- 可查看自己已提交的反馈摘要，但不可查看开发人员备注或内部处理信息。
- 单个会话允许多次反馈；相同消息可重复评价，但界面默认更新最近一次同类评价，避免误触造成重复记录。

### 2.2 开发人员

- 可查看、筛选和处理全部反馈。
- 可查看聚合后的运行问题、影响次数和关联会话。
- 可修改反馈与问题的处理状态及内部备注。
- 不可通过问题详情直接读取密码、Cookie、API Key、完整地址或原始敏感工具参数。

## 3. 信息架构

### 3.1 Dashboard 顶部与侧栏

- 顶部只保留当前模块标题、当前开发人员身份、刷新和退出。
- 删除页面标题下重复的 `Planner：... / 工具后端：... / 策略：...` 长文本。
- 侧栏底部新增“运行环境”紧凑区域，显示：
  - Planner 类型；
  - 工具后端名称和连接方式；
  - 策略是否加载；
  - 服务健康状态。
- 点击运行环境进入或展开配置详情；完整策略正文只在按需展开后显示。

### 3.2 Dashboard 导航

保留现有有效模块，并增加两个模块：

1. 概览；
2. 评测运行；
3. 任务回归；
4. 零售任务；
5. 工具与会话；
6. 对话测试；
7. 会话审计；
8. 用户反馈；
9. 问题中心；
10. 开发人员。

各页面职责：

| 页面 | 观测目标 | 主要有效性信号 |
| --- | --- | --- |
| 概览 | 系统整体状态 | 服务健康度、近 24 小时问题、待处理反馈、最近评测成功率 |
| 评测运行 | 离线能力与成本 | Reward、业务成功率、精确匹配率、Token 与成本 |
| 任务回归 | 版本退化 | Rule/LLM 差异、失败分类、动作偏差 |
| 零售任务 | 基准覆盖 | 用户目标、预期动作链、任务执行检查 |
| 工具与会话 | 工具基础设施 | MCP 状态、工具目录、原始调用结果、会话数量 |
| 对话测试 | Agent 行为 | 回复、工具调用、确认等待、连续运行停止原因 |
| 会话审计 | 写操作安全 | 写计划、显式确认、执行证据、状态变化 |
| 用户反馈 | 用户主观体验 | 满意度、标签、文字意见、待处理数量 |
| 问题中心 | 运行稳定性 | 严重程度、错误频次、影响会话、首次/最后发生时间 |
| 开发人员 | 控制台访问 | 账户状态、创建与禁用操作 |

## 4. 数据模型

新增迁移 `003_feedback_runtime_issues.sql`。

### 4.1 `user_feedback`

- `feedback_id TEXT PRIMARY KEY`
- `user_id TEXT NOT NULL REFERENCES users(user_id)`
- `conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id)`
- `message_id TEXT NULL REFERENCES messages(message_id)`
- `rating TEXT NOT NULL CHECK (rating IN ('helpful', 'not_helpful'))`
- `category TEXT NULL CHECK (category IN ('resolved', 'incorrect', 'unclear', 'slow', 'tool_failure', 'other'))`
- `comment TEXT NULL`
- `status TEXT NOT NULL CHECK (status IN ('new', 'reviewing', 'resolved', 'dismissed'))`
- `developer_note TEXT NULL`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`
- `resolved_by_user_id TEXT NULL REFERENCES users(user_id)`

索引：

- `(conversation_id, created_at)`；
- `(status, created_at)`；
- `(rating, category)`。

限制：`comment` 最多 2,000 字符；`developer_note` 最多 4,000 字符。普通用户 API 永不返回 `developer_note` 和 `resolved_by_user_id`。

### 4.2 `runtime_issues`

- `issue_id TEXT PRIMARY KEY`
- `fingerprint TEXT NOT NULL UNIQUE`
- `source TEXT NOT NULL CHECK (source IN ('api', 'planner', 'tool', 'mcp', 'database', 'frontend'))`
- `severity TEXT NOT NULL CHECK (severity IN ('warning', 'error', 'critical'))`
- `error_code TEXT NOT NULL`
- `summary TEXT NOT NULL`
- `sanitized_detail TEXT NULL`
- `status TEXT NOT NULL CHECK (status IN ('open', 'investigating', 'resolved', 'ignored'))`
- `occurrence_count INTEGER NOT NULL DEFAULT 1`
- `first_seen_at TEXT NOT NULL`
- `last_seen_at TEXT NOT NULL`
- `last_request_id TEXT NULL`
- `last_conversation_id TEXT NULL REFERENCES conversations(conversation_id)`
- `context_json TEXT NOT NULL DEFAULT '{}'`
- `developer_note TEXT NULL`
- `resolved_by_user_id TEXT NULL REFERENCES users(user_id)`
- `resolved_at TEXT NULL`

索引：

- `(status, severity, last_seen_at)`；
- `(source, error_code)`；
- `(last_conversation_id, last_seen_at)`。

### 4.3 错误指纹

指纹由以下稳定字段计算 SHA-256：

- 来源模块；
- 稳定错误码；
- 异常类型；
- 归一化调用位置或工具名称。

不使用错误消息中的订单号、用户 ID、邮箱或自由文本，避免同一故障因动态值被拆成多条，也避免敏感信息进入指纹输入。

## 5. 后端组件

### 5.1 仓储

在现有 SQLite Unit of Work 中增加：

- `FeedbackRepository`：创建、按用户/会话查询、开发人员分页筛选、更新处理状态；
- `RuntimeIssueRepository`：按指纹原子化新增或累加、分页筛选、详情读取、更新状态。

问题聚合必须在事务中完成。同一指纹再次出现时增加 `occurrence_count`，更新 `last_seen_at` 和最近关联信息，不覆盖首次发生时间。

### 5.2 服务

新增 `ObservabilityService`，职责如下：

- 验证反馈会话归属；
- 创建与读取用户反馈；
- 为开发人员提供反馈和问题查询；
- 更新处理状态与开发人员备注；
- 脱敏并记录运行问题；
- 计算概览指标。

该服务不负责 Agent 业务逻辑，不修改评测判定，也不将采集失败继续抛回客服链路。

### 5.3 错误采集

采集入口：

- FastAPI 全局未处理异常；
- Planner 调用失败或返回不可解析结构；
- 工具/MCP 连接、超时和非预期响应；
- SQLite 非预期异常；
- 前端 API 请求非预期失败上报。

不采集为系统问题：

- 用户未登录、权限不足等预期认证结果；
- 输入校验错误；
- 正常的待确认、用户拒绝或业务规则拒绝；
- 明确的资源不存在；
- 用户主动取消操作。

全局异常处理仍向浏览器返回稳定、中文、安全的错误响应。内部问题记录失败时只写本地标准日志，不覆盖原始业务响应。

## 6. API

### 6.1 普通用户 API

- `POST /api/v1/support/conversations/{conversation_id}/feedback`
- `GET /api/v1/support/conversations/{conversation_id}/feedback`

创建请求：

```json
{
  "message_id": "optional-message-id",
  "rating": "helpful",
  "category": "resolved",
  "comment": "问题已经解决"
}
```

### 6.2 开发人员 API

- `GET /api/v1/observability/feedback`
- `GET /api/v1/observability/feedback/{feedback_id}`
- `PATCH /api/v1/observability/feedback/{feedback_id}`
- `GET /api/v1/observability/issues`
- `GET /api/v1/observability/issues/{issue_id}`
- `PATCH /api/v1/observability/issues/{issue_id}`
- `GET /api/v1/observability/overview`

筛选参数包括状态、评分/严重程度、来源、分类、时间范围和关键词。第一版使用有上限的偏移分页；单页最大 100 条。

### 6.3 前端错误上报

- `POST /api/v1/observability/client-errors`

仅允许已登录用户调用，服务端重新脱敏并限制正文长度。前端不可指定严重程度为 `critical`，也不可提交任意堆栈全文；只接受页面、稳定错误码、请求路径、HTTP 状态和经过截断的安全摘要。

## 7. 客服中心体验

- Agent 回复区域提供低干扰的“有帮助”和“没帮助”图标按钮。
- 点击“有帮助”可直接提交，也可补充文字。
- 点击“没帮助”后显示分类选择和可选文字说明。
- 会话结束区域提供一次整体评价入口。
- 提交中禁用按钮；成功后显示已记录状态；失败时允许重试，不清空用户输入。
- 评价控件不得遮挡对话、确认操作或移动端输入框。

## 8. Dashboard 体验

### 8.1 用户反馈

- 顶部指标：待处理、负面反馈、今日新增、已解决。
- 筛选：状态、评分、分类和时间。
- 列表显示评价、分类、用户显示名、会话、摘要和时间。
- 详情显示关联消息上下文、用户文字和处理历史。
- 开发人员可设置状态与内部备注。

### 8.2 问题中心

- 顶部指标：开放问题、严重问题、近 24 小时次数、受影响会话。
- 筛选：状态、严重程度、来源、错误码和时间。
- 列表按 `critical > error > warning`、最近发生时间排序。
- 详情显示脱敏摘要、发生次数、首次/最后时间、最近请求/会话和安全上下文。
- 开发人员可设置状态与内部备注。

### 8.3 概览

概览从 `/api/v1/observability/overview` 读取：

- 服务健康状态；
- 近 24 小时运行问题次数；
- 开放严重问题数；
- 新反馈和负面反馈数；
- 最近一次评测业务成功率。

每个指标可点击进入对应筛选后的页面。无数据时显示明确的空状态，不以 `0` 掩盖加载失败。

## 9. 脱敏与安全

统一脱敏器处理以下键名及其常见变体：

- `password`、`temporary_password`；
- `authorization`、`cookie`、`session`、`token`、`api_key`；
- 邮箱、电话号码；
- 完整地址和支付字段；
- 工具参数中的自由文本原文。

保留诊断所需的安全信息：稳定错误码、模块、HTTP 状态、工具名称、字段名、参数类型和截断后的非敏感摘要。

问题详情使用文本节点渲染，不以 `innerHTML` 插入服务端错误内容。所有写接口执行角色检查、长度检查和枚举校验。

## 10. 失败策略

- 反馈写入失败：返回稳定错误码，界面保留输入并允许重试。
- 问题采集失败：记录标准日志，不影响原始请求处理。
- 问题中心加载失败：显示模块级错误，不影响其他 Dashboard 页面。
- 概览部分指标失败：按指标展示“暂不可用”，不让整个概览空白。
- 数据库迁移失败：应用拒绝启动并显示迁移编号，不在不完整 schema 上运行。

## 11. 验收标准

1. Dashboard 页面标题下不再重复显示 Planner 长文本。
2. 侧栏运行环境可以看到 Planner、MCP、策略和健康状态。
3. 已登录普通用户可以为自己的会话提交正面或负面反馈。
4. 普通用户不能为他人的会话提交或读取反馈。
5. 开发人员可以筛选、查看和更新反馈状态。
6. 相同错误指纹会聚合计数，不产生重复问题行。
7. API、Planner、工具/MCP、数据库和前端请求错误均有明确采集入口。
8. 预期的认证、校验、待确认和业务拒绝不被误报为运行问题。
9. 错误记录不包含密码、Cookie、API Key 或完整敏感参数。
10. Dashboard 问题中心能够查看严重程度、频次、影响会话和处理状态。
11. 概览指标可以跳转到对应筛选后的反馈或问题页面。
12. 新界面在 1440x900 和 390x844 下无横向溢出，导航、筛选和详情可用。
13. 数据库重启后反馈、问题聚合计数和处理状态仍然存在。
14. 现有认证、客服会话、评测、回归、工具、审计和开发人员管理测试保持通过。

## 12. 非目标与后续演进

本阶段不包含：

- 匿名反馈；
- 文件或截图附件；
- 自动向第三方发送问题；
- 邮件、短信或即时通信通知；
- Sentry、OpenTelemetry Collector 等外部部署；
- 多租户组织隔离；
- 错误自动修复或自动重新执行写操作。

后续部署到共享环境时，可由 `ObservabilityService` 的采集接口桥接 OpenTelemetry/Sentry，同时保留本地数据库作为产品内处理视图。
