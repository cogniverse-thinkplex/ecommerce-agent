# Agent 质量观测与回归中心设计

## 1. 目标

将当前由多个开发阶段页面拼接而成的 Dashboard，重构为面向真实开发与运营工作的 Agent 工程控制台。控制台必须支持以下闭环：

1. 观察 Agent 整体质量和运行趋势。
2. 从失败指标定位到具体会话、步骤、工具和错误。
3. 将运行问题或用户反馈转为可重放的回归用例。
4. 修复 Agent 后批量运行用例，并用结果验证问题是否解决。
5. 管理服务健康、模型、MCP、策略、数据源和开发人员账户。

本阶段保留本地准产品定位，不引入外部监控平台，也不接入真实电商数据库。

## 2. 用户与权限

工程控制台仅对 `developer` 角色开放。普通用户继续进入独立客服中心，不接触策略、工具名称、评测答案、Token、成本或原始 Trace。

开发人员可以查看脱敏后的运行数据、执行回归、管理回归用例和开发账户。直接调用写工具的 UI 将被移除，避免绕过 Agent 和确认门禁。

## 3. 最终信息架构

侧栏保留六个一级入口。

### 3.1 质量总览

作为登录后的默认页面，展示所选时间范围内的核心质量指标：

- 会话数、Agent 运行次数、用户消息数、工具调用次数。
- 业务成功数、失败数、成功率和错误率。
- 平均响应时间、P50/P95 响应时间和平均步骤数。
- 输入 Token、输出 Token、总 Token、目录价估算和单次平均成本。
- MCP、模型、工具和数据库错误率。
- 用户好评率、负面反馈数和未处理反馈数。
- 回归通过率、基准轨迹一致率、确认门禁成功率和落库成功率。

支持最近 24 小时、7 天、30 天和全部时间范围。页面同时展示成功率、调用量、延迟和错误的时间趋势，以及高频工具、高频失败工具和最近失败运行。

### 3.2 会话观测

合并现有“会话”“对话测试”和“会话审计”的生产观测部分。

- 按状态、Planner、模型、时间和错误筛选会话。
- 查看用户与 Agent 消息、运行步骤和停止原因。
- 查看每次工具调用的名称、耗时、结果状态和脱敏参数摘要。
- 查看写操作计划、确认 fingerprint、用户确认和数据库变化证据。
- 从失败会话创建回归用例。

沙盒对话不作为一级导航，放在回归中心的“沙盒调试”标签页中。

### 3.3 回归中心

合并现有“评测运行”“任务回归”“零售任务”和固定任务演示。

包含四个标签页：

1. `执行测试`：选择用例集、Planner、模型、最大步数和落库验证选项后运行。
2. `用例库`：管理 tau2 基准任务和从问题、反馈、会话创建的自定义用例。
3. `历史结果`：查看已保存运行、指标、成本、失败矩阵和任务详情。
4. `沙盒调试`：手工输入消息测试 Agent，不再提供任务 0/1/2 固定演示按钮。

Rule 与 LLM 双跑、历史对比和 smoke 集合均归入该模块。页面明确显示“本次运行”的 Planner、模型、工具后端和数据版本，不复用全局默认 Planner 文案。

### 3.4 问题中心

保留聚合错误能力，并增加：

- 查看错误首次/最近发生时间、次数、来源、影响会话和脱敏上下文。
- 关联一个或多个回归用例。
- 点击“添加为回归用例”，进入审核和预期结果补全流程。
- 查看关联用例最近运行结果。
- 只有关联用例通过后，才可标记“已验证解决”；仍允许“忽略”。

模型额度耗尽、网络瞬时错误等环境问题不会自动成为业务回归用例。开发人员必须审核后转换。

### 3.5 用户反馈

保留现有评价列表和处理状态，并增加：

- 跳转到关联会话。
- 从负面反馈创建回归用例。
- 关联修复用例及最近验证结果。
- 区分“已处理”和“已通过回归验证”。

### 3.6 系统管理

合并现有侧栏运行环境、工具后端和开发人员管理：

- API、SQLite 和 MCP 健康状态。
- 默认 Planner、当前 LLM、超时和输出上限。
- 工具后端、工具数量和 MCP 地址状态。
- Retail Policy 是否加载、策略摘要版本和数据版本。
- tau2 Retail 数据来源及商品、用户、订单、任务数量。
- 开发人员账户创建、启用和停用。

顶部仅保留紧凑状态，如“系统正常 · MCP 正常 · 无严重告警”。完整配置只在系统管理查看。

## 4. 删除和下沉的功能

从正式 Dashboard 删除以下独立入口或控件：

- 独立“评测运行”页面。
- 独立“任务回归”页面。
- 独立“零售任务”页面。
- 独立“工具与会话”页面。
- 独立“对话测试”页面。
- 独立“会话审计”页面。
- 侧栏常驻运行环境详情。
- 浏览器中的通用工具运行器。
- 取消订单写操作演示。
- 任务 0、1、2 固定演示按钮。

对应的底层 API、MCP 工具和自动化测试可以保留。只移除不适合真实系统的导航和直接操作入口。

## 5. 运行遥测模型

新增迁移，建立以下表。

### 5.1 `agent_runs`

一条记录代表一次由用户消息、沙盒测试或评测任务触发的 Agent 运行。

- `run_id`
- `conversation_id`
- `source`: `support`、`sandbox`、`benchmark`、`regression`
- `planner_type`
- `model`
- `tool_backend`
- `policy_version`
- `data_version`
- `status`: `running`、`succeeded`、`failed`、`waiting_confirmation`、`cancelled`
- `stopped_reason`
- `business_success`
- `confirmation_gate_success`
- `confirmed_outcome_success`
- `exact_match`
- `step_count`
- `prompt_tokens`、`completion_tokens`、`total_tokens`
- `estimated_cost_cny`
- `started_at`、`finished_at`、`duration_ms`
- `error_code`、`issue_id`

### 5.2 `agent_run_steps`

保存一次运行的可观测步骤，不保存未脱敏的模型思维过程。

- `step_id`、`run_id`、`sequence`
- `kind`: `planner`、`tool`、`guard`、`confirmation`、`response`
- `name`
- `status`
- `duration_ms`
- `summary_json`
- `started_at`、`finished_at`

工具调用次数、高频工具和工具错误率从 `kind=tool` 的步骤聚合，不再创建重复的工具指标表。

### 5.3 `regression_cases`

- `case_id`、`name`、`description`
- `origin_type`: `tau2`、`issue`、`feedback`、`conversation`、`manual`
- `origin_id`
- `fixture_type`: `tau2_task`、`conversation_replay`
- `fixture_json`: 脱敏输入、任务 ID、允许的数据快照引用
- `expected_json`: 业务结果、目标/禁止工具、确认和落库要求
- `status`: `draft`、`active`、`retired`
- `created_by_user_id`、`created_at`、`updated_at`

### 5.4 `regression_case_runs`

- `case_run_id`、`case_id`、`agent_run_id`、`batch_id`
- `status`: `queued`、`running`、`passed`、`failed`、`blocked`
- `failure_reason`
- `created_at`、`finished_at`

所有外键和查询索引随迁移创建。SQLite 继续使用 WAL、外键和显式事务。

## 6. 遥测采集边界

遥测由统一的 `RunTelemetryService` 负责，不在 API、Planner 和前端分别拼统计数据。

运行开始时创建 `agent_runs`，每个 Planner、Guard、工具和确认步骤记录起止时间；运行结束或异常时在 `finally` 路径完成记录。遥测写入失败不得破坏客服主流程，但必须写入应用日志并尝试生成 `database/telemetry_write_failed` 问题。

Token 和目录价只在供应商返回 usage 且本地存在价格表时记录。缺失值保持 `NULL`，不伪装成 0。

## 7. 指标定义

- `运行成功率 = succeeded / 已结束运行数`
- `业务成功率 = business_success=true / 可评估运行数`
- `错误率 = failed / 已结束运行数`
- `工具错误率 = failed tool steps / tool steps`
- `用户好评率 = helpful / 已评价反馈`
- `回归通过率 = passed case runs / 已结束 case runs`
- `P50/P95` 使用所选时间范围内 `duration_ms` 的离散百分位。
- 等待用户确认不算失败，单独显示为 `waiting_confirmation`。
- Rule Planner 不产生 Token 和模型成本，展示“未调用模型”，不展示 0 元。

所有指标支持按来源、Planner、模型和时间范围过滤。质量总览默认排除仍在运行的记录。

## 8. 问题转回归用例流程

1. 开发人员在问题、反馈或会话详情点击“添加为回归用例”。
2. 后端创建 `draft`，仅复制允许的脱敏字段和稳定数据引用。
3. 开发人员填写名称、预期业务结果、允许/禁止工具以及是否要求确认和落库。
4. 校验通过后激活用例。
5. 回归中心可单跑或批量执行。
6. 运行结果关联到来源问题或反馈。
7. 至少一次最新配置下的通过结果，才允许将问题标记为“已验证解决”。

对于无法稳定重放的外部故障，用例运行状态为 `blocked`，不计入 Agent 业务失败率。

## 9. API

新增或调整以下开发人员 API：

- `GET /api/v1/quality/overview`
- `GET /api/v1/quality/trends`
- `GET /api/v1/quality/tools`
- `GET /api/v1/runs`
- `GET /api/v1/runs/{run_id}`
- `GET /api/v1/regression/cases`
- `POST /api/v1/regression/cases`
- `PATCH /api/v1/regression/cases/{case_id}`
- `POST /api/v1/regression/cases/from-issue/{issue_id}`
- `POST /api/v1/regression/cases/from-feedback/{feedback_id}`
- `POST /api/v1/regression/cases/from-run/{run_id}`
- `POST /api/v1/regression/batches`
- `GET /api/v1/regression/batches/{batch_id}`
- `GET /api/v1/system/status`

现有评测和工具 API 暂时保留兼容，但新 UI 只通过新的聚合接口读取正式模块。

## 10. 错误、脱敏与安全

- API Key、Cookie、Authorization、密码和完整支付信息不得进入遥测或回归 fixture。
- 用户地址、邮箱和订单数据只保留重放所必需的字段；展示遵循现有开发人员权限。
- 运行异常必须完成失败遥测，并关联聚合问题 fingerprint。
- 回归创建接口拒绝缺少预期结果的激活请求。
- 浏览器不提供任意 MCP 写工具执行入口。

## 11. 实施顺序

1. 数据库迁移、Repository 和指标定义。
2. Runtime 遥测采集与问题关联。
3. 质量和运行查询 API。
4. 回归用例模型、转换流程和批量执行。
5. Dashboard 六模块重构和旧入口清理。
6. 数据回填、端到端验证和文档更新。

旧数据不伪造精确耗时。可以从现有会话、反馈、问题和已保存评测生成有限历史摘要，并明确标记为迁移数据；完整趋势从迁移上线后开始。

## 12. 验收标准

- Dashboard 只显示六个一级模块，移动端和桌面端均无重叠或溢出。
- 质量总览能展示调用量、成功率、失败率、延迟、Token、成本、工具和用户反馈指标。
- 一次客服消息和一次回归运行都能生成完整 `agent_runs` 记录。
- 可从问题、负面反馈和失败运行创建脱敏回归用例。
- 回归用例可单跑、批量运行并保存结果。
- 问题可查看关联用例及最新验证结果。
- 全局运行环境不再与回归页面本次 Planner 混淆。
- 正式 UI 不再包含通用工具运行器、写操作演示和固定任务演示按钮。
- 普通用户不能访问质量、问题、回归和系统管理 API。
- 现有客服中心、MCP 工具边界、确认门禁和 SQLite 恢复能力保持可用。
- 单元、API、迁移、权限、脱敏、指标计算和端到端 UI 测试全部通过。
