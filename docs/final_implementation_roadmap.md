# 最终实现路线与当前状态

本文档用于把当前原型收束到最终项目实现路线。后续开发以 `Adaptive_Ecommerce_Agent_Fullstack_Observability_Development_Plan.docx`、`README.md` 和本文档共同作为依据；其中 docx 负责完整设计，README 负责环境和运行说明，本文档负责阶段边界、当前进度和下一步优先级。

## 1. 当前判断

当前项目已经具备了一个可运行的 tau2 Retail 调试原型，但近期实现偏向“演示便利功能”：例如 Task 0/1/2 的固定演示按钮、规则式 proposal generator、前端回填任务提示等。这些功能可以帮助我们理解 benchmark 和验证工具链，但不能继续作为最终 Agent 的主线。

接下来要停止新增面向单个 task 的演示逻辑，转为实现最终需要的统一 Agent Runtime、评测执行器、可观测链路和前端工作台。

## 2. 当前已经完成的基础

可以保留并继续演进的部分：

- 本地 Conda/tau2 环境已经跑通，Retail benchmark 数据和官方工具环境可用。
- FastAPI 后端已经建立，具备健康检查、工具目录、session、trace、evaluation、retail task 等基础接口。
- `RetailToolPort` 和 `TauRetailAdapter` 已经把 tau2 Python 环境封装为统一业务工具边界。
- `GuardedRetailToolExecutor` 和 policy guard 已经实现读写工具分流，写操作需要 confirmation fingerprint。
- session service 已经能记录消息、工具提案、工具结果、pending confirmation 和 trace timeline。
- evaluation 侧已经能读取本地 tau2 simulation runs，展示 reward、cost、summary、compare。
- dashboard 已经有中文界面，可以查看任务、session、trace、工具调用、评测结果和当前会话与 task expected actions 的差异。
- 后端测试已经覆盖 API、工具适配、guard、session、trace、evaluation 等基础模块，最近一次全量测试为 `98 passed`。

这些是最终系统的地基，不需要推倒重来。

## 3. 需要收束或替换的原型逻辑

以下内容后续只保留为调试辅助或测试基线，不再作为产品主线继续堆功能：

- 针对 Task 0/1/2 的固定演示按钮。
- 前端拼接 prompt、自动回填任务文本、人工驱动某条 task 的演示流程。
- 规则式 `RuleBasedProposalGenerator` 中对具体商品、订单、任务路径的硬编码。
- 当前 `auto-run` 对同一段用户消息重复推进的简化循环。
- 只用于“看起来能跑”的 dashboard 控制逻辑。

正确方向是：前端只负责输入、确认、观察和评测管理；真正的业务推进由后端统一 Agent Runtime 完成。

## 4. 新的阶段路线

### 阶段 A：Agent Runtime 边界重构

目标：把“规则演示原型”收束成一个可替换、可测试、可评测的 Agent Runtime。

要做的事：

- 定义统一的 `AgentRuntime` / `AgentOrchestrator` 接口，覆盖单步推进、连续运行到阻塞、确认/拒绝、重置等能力。
- 把当前 rule-based generator 降级为 baseline runtime，只用于回归测试和极小流量 fallback。
- 建立 LLM-backed runtime 的正式骨架：模型配置、结构化 tool proposal、JSON schema 校验、错误恢复、工具执行、最终回复生成。
- FastAPI、评测 runner、dashboard 全部只依赖 runtime 接口，不直接依赖某个 demo generator。

验收标准：

- 同一个用户请求可以通过 runtime 接口推进，不依赖前端演示按钮。
- 写工具仍然必须经过 guard 和 confirmation。
- 至少用 fake LLM client 和 tau2 adapter 覆盖单元测试。

当前状态：未完成，是下一步最高优先级。

### 阶段 B：真实 Retail Agent 能力

目标：实现最终要用的客服 Agent，而不是只跑几个固定 demo。

要做的事：

- 加入明确的状态机或 LangGraph 图：认证、意图识别、上下文构建、工具提案、guard、确认、工具执行、回复生成。
- 将订单查询、取消、修改、退货、换货、商品咨询、人工转接做成 Skill/Policy 层能力。
- 使用 tau2 Retail policy、任务信息和工具 schema 约束模型，不把业务规则散落在前端或 demo 代码里。
- 让 Agent 面对任意 Retail task 时自己决定下一步，而不是由页面按钮决定。

验收标准：

- 能在一批 tau2 Retail tasks 上自动运行，产出完整 trajectory。
- 不针对 task id 写特殊逻辑。
- reward、失败原因、工具轨迹、cost 都可记录。

当前状态：只有雏形；rule-based 逻辑可作为理解样例，但不是最终实现。

### 阶段 C：评测与回归系统

目标：把 tau2 benchmark 变成我们日常开发的回归基准。

要做的事：

- 实现后端 evaluation runner，支持选择任务集、模型、运行次数和输出目录。
- 每次运行保存结果、trace、tool calls、reward、cost、失败分类。
- 提供 run compare，比较不同模型、不同 prompt、不同 runtime 版本。
- 对失败任务提供“expected actions vs actual actions”的结构化诊断。

验收标准：

- 改动 Agent 后能一键跑小集合回归。
- dashboard 能看出 reward 变化、cost 变化和失败样例。

当前状态：结果读取和对比已经有基础；真正的 runner 和失败诊断还需要补齐。

### 阶段 D：可观测工作台

目标：前端从“演示控制台”转为“Agent 工程工作台”。

要做的事：

- 保留中文界面。
- Chat 区只负责真实对话和 confirmation。
- Trace 区展示 runtime 每一步：模型输入输出、tool proposal、guard 决策、工具结果、回复。
- Eval 区管理 benchmark runs、对比结果、失败样例和成本。
- Tool 区作为调试入口，但不再驱动主流程。

验收标准：

- 用户可以在前端输入任意 Retail 用户请求进行测试。
- 每个会话都能追踪到完整 runtime 事件。
- 前端不再需要 task demo 按钮才能验证 Agent。

当前状态：已有可用 dashboard，但定位仍偏调试/演示；需要按 runtime 重整。

### 阶段 E：MCP 工具管理与生产后端

目标：让工具调用进入最终架构，而不是只停留在 tau2 Python adapter。

要做的事：

- 保留 `TauRetailAdapter` 作为 benchmark backend。
- 在同一个 `RetailToolPort` 边界下新增 MCP adapter 或 MCP bridge。
- 明确哪些 tool 由 MCP 管理、哪些是内部服务工具。
- 加入 provider config、超时、重试、限流、审计日志和错误码。

验收标准：

- dashboard 能准确显示当前工具后端是否由 MCP 管理。
- Agent Runtime 不关心工具来自 tau2、MCP 还是生产数据库。

当前状态：接口边界已预留，MCP backend 尚未实现。

### 阶段 F：持久化、部署与演进

目标：从本地原型转为可持续开发和部署的系统。

要做的事：

- 引入 PostgreSQL/pgvector/Valkey，持久化 session、trace、evaluation、memory、experience。
- 建立 Docker Compose 本地开发环境。
- 建立 CI 测试和 benchmark smoke test。
- 准备 Kubernetes 部署配置。
- 后续再加入 RAG、Memory、Critic、Reflection、Skill Evolution。

验收标准：

- 本地可以一键启动完整栈。
- session 和 eval run 可长期保存。
- CI 能防止核心 Agent 能力回退。

当前状态：尚未开始。

## 5. 现在处于什么步骤

当前项目处在“阶段 B 第一轮已经开始，真实 Retail Agent 能力开始落地”的位置。

更准确地说：

- 环境、tau2 数据、后端骨架、工具边界、guard、trace、评测读取、中文 dashboard 已经完成到可用原型。
- 最终 Agent Runtime 的第一层边界已经落地：`AgentSessionService` 通过 `AgentRuntime` 接口推进对话，默认使用 runtime 实现推进主链路。
- Skill registry、planner decision、skill action routing、tool/schema/skill-policy 校验已经接入 runtime。
- tau2 Retail task smoke 已经开始覆盖真实任务前缀，不再只靠 dashboard demo 按钮验证。
- MCP 工具管理还没有接入。
- 持久化数据库、RAG、Memory、Critic、Skill Evolution、部署都还没有进入正式实现。

所以后续不应该继续加更多 demo task，而应该继续推进阶段 B，把认证、订单查询、写操作确认等能力节点化，并用 tau2 task subset 做回归。

## 6. 下一步执行建议

阶段 A 第一轮已经完成：

- 新增 `backend/app/agent/runtime.py`，定义 `AgentRuntime`、`AgentTurnResult`、`AgentAutoRunResult` 和 `BaselineAgentRuntime`。
- `AgentSessionService.run_turn` 和 `AgentSessionService.auto_run` 已改为委托 runtime，并保存 runtime 返回的 state。
- 默认 API 服务新增 `build_agent_runtime(executor)` 构建入口，后续 runtime 替换不需要改 session/API 主流程。
- 当前 rule-based / LLM proposal generator 都被收束到 baseline runtime 后面，不再直接作为 session service 的主边界。
- 新增 runtime 单元测试和 service 委托测试。

阶段 A 第二轮已经完成：

1. LLM proposal generator 已经接收工具目录、policy 和最近消息上下文，prompt 中包含 `AVAILABLE_TOOLS`、`POLICY`、`RECENT_MESSAGES` 和最新用户消息。
2. `build_agent_runtime(executor)` 在 LLM 模式下会把 `executor.list_tools()` 和 `executor.policy` 注入 planner。
3. Runtime 在进入 executor 前做工具白名单校验；未知工具会被拒绝并记录 `tool_proposal.rejected`。
4. Runtime 在进入 executor 前检查 JSON schema 中的 `required` 参数；缺参会被拒绝并记录 `tool_proposal.rejected`。
5. 新增 fake LLM 端到端测试，覆盖“LLM proposal -> runtime validation -> policy guard -> pending confirmation”。

阶段 A 第三轮已经完成：

1. LLM planner 输出已经从宽松 `ToolProposal | None` 升级为显式 `PlannerDecision`，支持 `tool_call`、`final_response`、`need_more_info`、`invalid`。
2. `LLMProposalGenerator.decide()` 作为新版 planner 入口；旧的 `generate()` 仍保留兼容，用于返回 tool proposal。
3. Runtime 会消费 `PlannerDecision`：`final_response` 和 `need_more_info` 会追加 assistant message，并记录 `planner.final_response` / `planner.need_more_info`。
4. Planner JSON 解析失败、非法 action、schema 不匹配会进入 `invalid` 决策，并由 runtime 记录 `planner.invalid_output`。
5. LLM 分支已经有明确的 `LLMPlannerRuntime`，配置层在 LLM 模式下返回它；规则分支继续使用 `BaselineAgentRuntime`。

阶段 A 第四轮已经完成：

1. 新增最小 `SkillRegistry` / `SkillDefinition`，覆盖 `authentication`、`order_lookup`、`cancel_order`、`return_order`、`exchange_order`、`product_info`。
2. 每个 skill 现在声明 `allowed_tools`、`required_state` 和 `requires_confirmation`，先作为 runtime 边界，不把业务规则继续散在 planner prompt 里。
3. `PlannerDecision` 和 `ToolProposal` 已支持 `skill_id` / `skill_action`，LLM prompt 中会暴露 `AVAILABLE_SKILLS`。
4. Runtime 在进入 executor 前执行 skill-policy 校验：planner 提案的 tool 不在 skill 的 `allowed_tools` 中会被拒绝，并记录 `skill_policy.rejected`。
5. 默认 API 构建路径会把同一份 default skill registry 注入 LLM planner prompt 和 runtime 校验层。
6. 新增 tau2 Retail runtime smoke test，验证真实 `TauRetailAdapter + AgentSessionService + runtime` 能完成一条用户查找轨迹。

阶段 B 第一轮已经完成：

1. `SkillDefinition` 新增 `actions` 映射，runtime 可以从 `skill_id + skill_action` 路由到具体 tool。
2. 新增 skill action router：planner 可以只输出 skill/action，runtime node 负责补齐 tool，并记录 `skill_node.routed`。
3. 非法 skill/action 会在进入 tool/schema/guard 前被拒绝，并记录 `skill_node.rejected`。
4. 写操作 skill action 已覆盖：`cancel_order/cancel_pending_order` 会路由到写工具，并由 policy guard 停在 pending confirmation。
5. Rule baseline 增强为可识别 tau2 known_info 中的 “You are Yusuf Rossi in zip code 19122”，并避免认证结果已有时重复认证。
6. 新增 tau2 Retail Task 0 runtime smoke：真实 `TauRetailAdapter + AgentSessionService + runtime` 能跑到写操作确认前，并匹配 expected actions 前缀。

阶段 B 第二轮已经完成：

1. Runtime 主链路已经拆出明确 node 模块：`planner_node` 负责 planner decision，`skill_node` 负责 skill/action 到 tool 的路由，`proposal_validation_node` 负责 tool/schema 与 skill policy 校验。
2. `runtime.py` 现在只保留 turn/auto-run 编排、消息追加和 executor 调用，不再承载节点内部规则。
3. 新增 `run_retail_task_subset(task_ids, max_steps=...)`，可以按 tau2 Retail task id 运行真实 runtime，并返回停止原因、conversation id 和 action prefix/check 结果。
4. 新增节点级测试覆盖 planner 终止响应、非法 planner 输出、skill/action 路由、非法 skill/action、未知工具、缺参和 skill policy 越界。
5. 新增 subset runner 集成测试，确认 task 0 能跑到写操作确认前，并匹配 expected actions 前缀。

阶段 B 第三轮已经完成：

1. 新增 `POST /evaluations/runtime-subset`，可以提交 `task_ids` 和 `max_steps`，直接调用真实 runtime subset runner。
2. API 返回每个 task 的 `stopped_reason`、`conversation_id` 和完整 `SessionTaskCheck`，包含 `matched_prefix_count`、`missing_actions`、`unexpected_actions`。
3. Dashboard 新增“任务批量回归”面板，可以输入逗号分隔 task id，触发真实 runtime 回归，并在中文界面展示匹配前缀、是否全匹配、实际/缺失/额外动作。
4. LLM planner prompt 已调整为优先输出 `skill_id` / `skill_action`，底层 `tool_name` 只作为无合适 skill 时的兼容提示。
5. 新增 API 和静态页面测试，覆盖 runtime subset 接口、参数校验和 dashboard 中文入口。

阶段 B 第四轮已经完成：

1. Runtime subset runner 新增 `RuntimeSubsetArtifact`，可以把小批量运行结果保存为 `simulations/<run_name>/runtime_subset.json`。
2. `POST /evaluations/runtime-subset` 新增 `save_artifact` / `run_name`，保存后返回 artifact 元数据和 `artifact_url`。
3. 新增 `GET /evaluations/runtime-subset/{run_name}`，可以读取已保存的小批量回归 artifact。
4. 每个 runtime subset result 新增 `diagnostic`，包含第一处动作偏差位置、预期动作、实际动作和中文诊断文案；全匹配时明确显示“动作序列完全匹配”。
5. Dashboard 顶部显示当前 `Planner` 类型，任务批量回归面板新增快速选择任务、保存 artifact 选项和“第一处偏差”展示。
6. 新增测试覆盖 artifact 保存/读取、planner config API、dashboard 快速选择入口和诊断渲染入口。

阶段 C 第一轮已经完成：

1. 评测索引现在能识别两类运行：tau2 `results.json` 和 runtime subset `runtime_subset.json`。
2. `/evaluations/{run_name}/summary` 新增统一 summary 入口，runtime subset 会汇总 task 数、task id、精确匹配率和平均匹配前缀。
3. `/evaluations/compare` 已纳入 runtime subset artifact，对比结果新增 `run_type`、`exact_match_rate` 和 `average_matched_prefix_count`。
4. Dashboard 评测对比表新增运行类型和精确匹配列，已保存的小批量回归可以和 tau2 simulation run 一起浏览。
5. 新增测试覆盖 runtime subset artifact 在 index、summary、compare 和 API 层的表现。

阶段 C 第二轮已经完成：

1. Runtime subset artifact 的每个 task result 现在包含 `trace_entries`，保存关键 message/event trace 摘要。
2. 每个 task result 新增 `action_timeline`，逐项展示 expected action、actual action、是否匹配，以及对应的 trace sequence。
3. Dashboard 对比表中点击“小批量回归”运行，会加载 `/evaluations/runtime-subset/{run_name}` artifact 详情。
4. Artifact 详情会展示每个 task 的动作时间线、第一处偏差和 trace 事件列表。
5. 新增测试覆盖 artifact trace/action timeline 字段、API 保存读取和 dashboard 详情入口。

阶段 C 第三轮已经完成：

1. `/config` 已扩展为返回 planner 类型、模型名、tool backend 信息和当前 policy 摘要。
2. Dashboard 顶部配置展示已显示 rule/llm、模型、工具后端是否 MCP 管理，以及 policy 摘要。
3. Runtime subset `action_timeline` 已聚合 tool proposal rationale，并预留/填充 rejection reason 字段。
4. Artifact 详情页的动作时间线会展示 rationale 或 rejection reason，让失败诊断开始具备“为什么偏了”的解释入口。
5. 新增测试覆盖 config API、前端配置展示、timeline rationale/rejection 字段。

阶段 C 第四轮已经完成：

1. Runtime subset runner 新增 `planner_type`，支持 `rule` 和 `llm` 两种 planner。
2. `planner_type` 会写入每个 task result 和保存后的 `runtime_subset.json` artifact。
3. `POST /evaluations/runtime-subset` 新增 `planner_type` 请求字段；选择 `llm` 时会使用同一套 TauRetailAdapter、skill registry 和 LLMPlannerRuntime。
4. Dashboard “任务批量回归”面板新增 Planner 模式选择器，可以用同一组 task 运行 rule baseline 或 LLM planner。
5. Artifact 详情会展示每个任务使用的 planner 类型，便于后续横向比较。
6. 新增测试覆盖 runner artifact、API 请求和前端选择器。

阶段 C 第五轮已经完成：

1. Runtime subset artifact 新增 `summary`，保存 task 总数、精确匹配数、失败 task id、动作偏差 task id 和 stopped reason 分布。
2. 新 artifact 会写入 summary；旧 artifact 读取时仍兼容缺省 summary，避免历史结果无法打开。
3. Dashboard “任务批量回归”面板新增结果筛选：仅看失败、仅看动作偏差。
4. Artifact 详情顶部新增 summary 卡片，显示总任务、全匹配、失败任务、动作偏差、停止原因和当前筛选数量。
5. Dashboard 新增“一键双跑”，会用同一组 task 顺序运行 rule baseline 和 LLM planner，并保存两个 artifact。
6. 一键双跑结果会在当前面板合并展示，任务卡片显示 rule/llm 分组，便于直接观察同一 task 的行为差异。
7. 新增测试覆盖 artifact summary、筛选入口和一键双跑入口。

阶段 D 第一轮已经完成：

1. “一键双跑”完成后会按 task id 对齐 rule baseline 和 LLM planner 的结果，不再只是把两组卡片简单合并。
2. Dashboard 新增 `Rule vs LLM 差异` 区块，每个 task 一张 diff 卡，左右展示 rule/LLM 的 stopped reason、全匹配、匹配前缀、第一处偏差和实际动作序列。
3. Diff 卡会标记“有差异/一致”，并单独显示动作序列是否不同。
4. 双跑结果仍保留 summary 和筛选能力；筛选后只展示命中筛选条件的 task diff。
5. 新增前端静态测试覆盖 diff 渲染函数、对齐函数和中文展示文案。

阶段 D 第二轮已经完成：

1. Runtime task result 新增 `failure_summary`，聚合 failure category、rejection event、planner terminal event、planner message、first mismatch 和推荐排查方向。
2. `failure_summary` 会识别 `planner.final_response`、`planner.need_more_info`、`planner.invalid_output`、`*.rejected`、动作偏差、pending confirmation 和 max steps 等类型。
3. Runtime subset artifact 会把每个 task 的 failure summary 写入 `runtime_subset.json`，旧 artifact 仍可通过前端 fallback 推断基础原因。
4. Dashboard 新增“失败原因矩阵”，按 task、planner、stopped reason、失败类型、事件、详情和推荐排查方向展示。
5. 普通 artifact 详情和 rule vs LLM diff 视图都会显示失败原因矩阵，并与当前筛选条件保持一致。
6. 新增测试覆盖后端 failure summary 字段和前端矩阵入口。

阶段 D 第三轮已经完成：

1. Dashboard 新增“运行 smoke 集合”按钮，固定运行 Retail task `0,1,2`。
2. Smoke 集合使用当前 Planner 模式和最大步数，强制保存 artifact，便于每次改动后留存回归证据。
3. Smoke artifact 使用稳定命名 `smoke-<planner>-<timestamp>`，例如 `smoke-rule-20261002T150000Z`。
4. Smoke 运行完成后会直接渲染 artifact 详情，包含 summary、失败原因矩阵、动作时间线和 trace。
5. README 新增日常开发验收流程：先跑单 task，再跑 smoke 集合，再按需一键双跑和查看失败原因矩阵。
6. 新增前端静态测试覆盖 smoke 按钮、固定 task 集合、run_name 和 smoke 运行函数。

阶段 D 第四轮已经完成：

1. Evaluation index、summary 和 compare 已能识别 `smoke-*` artifact，新增 `run_group`、`is_smoke` 字段。
2. Runtime subset summary 新增 `failure_categories` 聚合，用于展示 smoke 中各类失败原因分布。
3. Dashboard 评测对比表会把 smoke runtime subset 标记为“小批量回归 / smoke”。
4. Dashboard 新增“最近 smoke 结果”面板，展示最近 smoke artifact 的精确匹配率、任务数和失败类型分布。
5. 点击最近 smoke 卡片可以直接打开对应 runtime subset artifact 详情，继续查看失败原因矩阵、动作时间线和 trace。
6. 新增测试覆盖 smoke artifact 的 index/summary/compare 字段和前端 smoke 视图入口。

阶段 D 第五轮已经完成：

1. 新增 smoke 历史对比 helper，可按 task id 对齐两个 `smoke-*` artifact，并标记 regression、improvement、unchanged、added、removed。
2. 新增 `GET /evaluations/smoke/compare` API，前端和外部工具可以复用同一份 smoke 对比逻辑。
3. Dashboard “最近 smoke 结果”面板新增 `smoke 历史对比` 按钮，默认比较最近两个 smoke artifact 并显示任务级差异。
4. 新增 CLI wrapper `scripts/compare_smoke_runs.sh`，可以在命令行输出 baseline/candidate、regression/improvement 数量和每个 task 的变化。
5. README 新增 smoke 历史对比和 CLI 报告用法。
6. 新增测试覆盖 smoke 对比 helper、API、CLI 和前端入口。

阶段 E 第一轮已经完成：

1. 新增 `app.evaluation.runtime_smoke`，可运行固定 smoke task `0,1,2`，保存 runtime subset artifact，并可选生成 Markdown 报告。
2. 新增 `scripts/run_runtime_smoke.sh`，一条命令可运行 rule/llm smoke，并通过 `--report-path` 输出报告。
3. Smoke Markdown 报告包含 planner、task ids、exact match、failure categories、可选 smoke diff 和候选改进建议。
4. 候选改进建议会根据 failure categories 给出动作偏差、planner 终止、runtime rejection、max steps 等排查方向。
5. README 新增一键运行 smoke 并生成 Markdown 报告的命令示例。
6. 新增测试覆盖报告生成、候选改进建议和固定 smoke task 集合。

阶段 E 第二轮已经完成：

1. 新增 `app.evaluation.runtime_smoke_pair`，一条编排链路会依次运行 rule smoke 和 LLM smoke。
2. 新增 `scripts/run_runtime_smoke_pair.sh`，默认生成 `smoke-rule-<timestamp>`、`smoke-llm-<timestamp>` 两个 artifact。
3. 双跑完成后会自动调用 smoke compare，对齐 task id 并生成 regression / improvement diff。
4. Markdown diff report 默认归档到 `docs/smoke/smoke-pair-<timestamp>.md`，方便形成按日期追踪的回归记录。
5. README 新增双跑命令和 API 额度提醒。
6. 新增测试覆盖双跑编排、CLI 输出、artifact 对比和报告归档。

阶段 E 第三轮已经完成：

1. 已实际运行 `run_runtime_smoke_pair`。`dashscope/deepseek-v4-pro-0813` 在真实运行中返回免费额度耗尽，因此按既定备用模型策略切换到 `dashscope/qwen3.7-flash` 完成 smoke。
2. 真实产物已保存：
   - `benchmarks/data/simulations/smoke-rule-20261013T025541Z/runtime_subset.json`
   - `benchmarks/data/simulations/smoke-llm-20261013T025541Z/runtime_subset.json`
   - `docs/smoke/smoke-pair-20261013T025541Z.md`
3. 本轮真实结果：rule baseline `2/3` exact match，LLM planner `0/3` exact match，LLM 相比 rule 有 `2` 个 regression、`0` 个 improvement。
4. LLM 失败聚类集中在 `planner_terminal`：task 0 为 `planner.invalid_output`，task 1 为过早 `planner.final_response`，task 2 为过早 `planner.need_more_info` 且出现额外 catalog lookup。
5. 已输出第一版 Critic/Reflection 候选改进建议文档：`docs/smoke/critic-reflection-20261013T025541Z.md`。
6. 候选建议文档结构已固定为：运行证据、结果摘要、失败聚类、代表 task、疑似原因、候选 prompt/skill/tool schema 改动、复测命令和 regression gate。

阶段 E 第四轮已经完成：

1. LLM planner system prompt 已强化为 JSON-only 输出契约，明确禁止 Markdown/prose 包裹，并补充写操作前不可过早 `final_response`、已知商品/订单线索时避免 `list_all_product_types`。
2. `LLMProposalGenerator.decide()` 新增一次 invalid JSON repair：首次解析失败时，会把原始输出和错误交给模型修复成单个 JSON object；修复仍失败才返回原 invalid 决策。
3. `LLMPlannerRuntime` 新增 terminal fallback：当 LLM 输出 `invalid` / `final_response` / `need_more_info`，但确定性 baseline 能从当前状态推出下一步工具时，会继续执行 fallback 工具，并记录 `planner.terminal_fallback`。
4. 新增 fake LLM 测试覆盖 invalid JSON repair、repair 失败保留错误、提前 final response 时 fallback 到 exchange 写操作、invalid 后 fallback 到订单查询。
5. 复跑真实 `qwen3.7-flash` smoke pair：
   - `benchmarks/data/simulations/smoke-rule-20261013T030935Z/runtime_subset.json`
   - `benchmarks/data/simulations/smoke-llm-20261013T030935Z/runtime_subset.json`
   - `docs/smoke/smoke-pair-20261013T030935Z.md`
6. 本轮真实结果：LLM exact match 从上一轮 `0/3` 提升到 `1/3`，task 0 已达到 rule baseline 的 pending confirmation，regression 数从 `2` 降到 `1`。
7. 新增 Critic/Reflection 文档：`docs/smoke/critic-reflection-20261013T030935Z.md`，把剩余问题收束为重复读动作循环和 unknown tool repair。

阶段 E 第五轮已经完成：

1. `LLMPlannerRuntime` 新增 repeated-read detection，针对 `find_user_id_by_name_zip`、`get_user_details`、`get_order_details` 这类身份/订单读工具，发现已有结果时会尝试确定性 fallback。
2. 当 exchange 所需订单和商品详情已经齐备、但 planner 重复读用户/订单时，会 fallback 到 `exchange_delivered_order_items`，并记录 `planner.repeated_read_fallback`。
3. `LLMProposalGenerator` 新增 `repair_rejected_tool()`，对 `unknown_tool` rejection 提供一次 LLM repair，输入 rejected tool 和 `AVAILABLE_TOOLS`，要求改写为合法 `tool_call`。
4. Runtime 接入 `planner.rejected_tool_repair`，repair 成功后仍重新走 tool schema、skill policy 和 guard 校验。
5. 修复 failure summary 优先级：动作 exact match 且停在 pending confirmation 时，后续 incidental rejection 不再把类别误标为 `rejected`。
6. 新增 fake LLM 测试覆盖 repeated-read fallback、unknown tool repair、exact pending confirmation 的 failure summary 优先级。
7. 复跑真实 `qwen3.7-flash` smoke pair：
   - `benchmarks/data/simulations/smoke-rule-20261013T111309Z/runtime_subset.json`
   - `benchmarks/data/simulations/smoke-llm-20261013T111309Z/runtime_subset.json`
   - `docs/smoke/smoke-pair-20261013T111309Z.md`
8. 本轮真实结果：LLM exact match 达到 `2/3`，与 rule baseline 一致；smoke compare 显示 `regressions=0`、`improvements=0`、`unchanged=3`。task 0/1 均已达到 rule baseline 的 pending confirmation 行为。
9. 新增 Critic/Reflection 文档：`docs/smoke/critic-reflection-20261013T111309Z.md`，把剩余问题收束为 task 2 return flow 仍使用 catalog browsing。

阶段 E 第六轮已经完成：

1. `LLMPlannerRuntime` 新增已知商品护栏：当模型在明确 T-Shirt 线索下提出 `get_user_details` 或 `list_all_product_types`，会优先替换为定向 `get_product_details`，并记录 `planner.known_product_fallback`。
2. Return 确定性流程已补全为：定向商品查询、读取已认证用户订单列表、按未检查顺序读取订单、定位 delivered order 后生成 `return_delivered_order_items` 待确认操作。
3. Unknown tool repair 改为确定性 fallback 优先；只有当前状态无法推出合法下一步时才调用一次 LLM repair，避免把未知工具修成无关的人工转接。
4. 对合法 `tool_name` 携带错误 skill 元数据的情况新增归一化：未知 skill action 使用确定性 fallback，未知 skill id 会移除元数据后重新执行 tool schema、skill policy 和 Guard 校验；`tool_not_allowed` 仍保持拒绝。
5. Return skill 和 planner prompt 已明确混合“商品信息 + 退货”请求的顺序，并禁止已知商品名时做全目录枚举。
6. 首次真实 smoke 暴露 `transfer_to_human_agents` 回归，产物为 `smoke-*-20261015T053240Z`；修复后再次运行 `qwen3.7-flash`：
   - `benchmarks/data/simulations/smoke-rule-20261015T054149Z/runtime_subset.json`
   - `benchmarks/data/simulations/smoke-llm-20261015T054149Z/runtime_subset.json`
   - `docs/smoke/smoke-pair-20261015T054149Z.md`
7. 最终真实结果保持 LLM `2/3` exact match、`regressions=0`。task 0/1 均精确匹配并进入 pending confirmation；task 2 不再出现 `list_all_product_types` 或人工转接，并按 `find user -> T-Shirt -> user details -> order details` 推进。
8. 使用 rule runtime、真实 tau2 数据和 `max_steps=10` 单独验证 task 2，可完整推进到 `return_delivered_order_items` pending confirmation。
9. 最终后端回归为 `171 passed`；保留 tau2 `audioop` 的一条既有弃用警告。
10. 新增 Critic/Reflection 文档：`docs/smoke/critic-reflection-20261015T054149Z.md`。

阶段 E 第七轮已经完成：

1. Runtime task check 已区分 `exact_match` 与 `business_success`。严格动作序列继续用于轨迹审计，最终目标写操作正确进入 confirmation gate 时则记为业务成功。
2. 固定 smoke 支持按任务配置 step budget；task `0`、`1` 保持默认 `6` 步，较长的 return task `2` 使用 `10` 步。
3. Runtime subset artifact、summary、评测对比、smoke diff、Markdown 报告和 Dashboard 均已展示业务成功指标，并兼容旧 artifact。
4. 已恢复的 planner rejection/fallback 会记录在 `recovery_kinds` 中，不再自动把已恢复任务归类为 `rejected`。
5. 当业务目标已完成但严格轨迹不同，failure summary 使用 `business_success` 分类；Dashboard “仅看失败”按业务结果筛选，动作偏差仍可独立筛选。
6. 已使用真实 tau2 本地数据重新运行 rule smoke：task `0/1/2` 业务成功 `3/3`，严格匹配 `2/3`，task `2` 在 10 步内进入 `return_delivered_order_items` confirmation gate。
7. 本轮没有调用付费模型 API；改动属于评测语义和预算编排，使用确定性 rule replay 与全量测试验证。

下一步建议进入阶段 E 第八轮：

1. 从固定 3 个 task 扩展为覆盖 exchange、return、cancel、address/payment update 等代表性业务簇的小型回归集。
2. 将业务成功判定从“最终目标写操作进入 confirmation gate”扩展为可配置 outcome evaluator，并覆盖确认后状态变更和关键参数正确性。
3. 为回归集增加按场景聚合的成功率、严格匹配率、平均步骤数和 cost，形成可比较的质量门槛。
4. 只有涉及 planner prompt、skill routing 或 fallback 行为变化时再运行真实 LLM smoke，以控制 API 消耗。

阶段 E 第八轮已经完成：

1. 新增通用 `BusinessOutcomeCheck`，从 task expected actions 中识别目标写操作，并严格比较工具名和完整参数；工具名正确但参数错误不再计为业务成功。
2. Runtime runner 新增可选确认后验证：仅对匹配的 pending write 自动确认，在隔离 tau2 环境执行，并结合工具执行事件和数据库哈希变化判定 `confirmed_state_verified`。
3. Runtime artifact 新增 `step_count`、`cost`、outcome evidence、总体业务成功率、严格匹配率、平均步骤、总/平均成本和场景聚合指标；旧 artifact 缺字段时保持默认兼容。
4. 新增代表性回归清单：换货 task `0`、退货 task `2`、取消 task `38`、地址修改 task `17`、支付修改 task `40`，每类能力均有稳定 task id 和独立步数预算。
5. 新增 `scripts/run_runtime_regression.sh`，可生成代表集 artifact 和 Markdown 报告；Dashboard artifact 详情新增“业务结果证据”和“场景指标”。
6. 评测索引新增 `regression` 分组，统一 summary/compare 会展示代表集平均步骤及逐任务真实记录成本；无 provider usage 时成本明确为 `0`。
7. 已使用真实 tau2 本地数据运行 rule baseline：业务成功 `2/5`、严格匹配 `1/5`、平均步骤 `3.00`。换货和退货均完成确认执行与数据库状态变化验证。
8. 当前能力缺口被明确量化为 `cancel`、`address_update`、`payment_update`，三者均为 `target_not_reached`，没有针对 task id 添加 planner 捷径。
9. 本轮未调用付费模型 API。
10. 独立审查后完成三项加固：自动确认前重新核对当前 pending action 的工具、完整参数和 fingerprint；拆分 `confirmation_gate_success` 与 `confirmed_outcome_success`；LLM usage 不可用时成本保存为 `null/N/A`，不再误报为零。
11. 数据库哈希不可用与已验证但未变化分别使用 `state_verification_unavailable`、`state_unchanged`，失败原因可直接区分。

下一步建议进入阶段 E 第九轮：

1. 为 rule baseline 增加通用 email/name+zip 身份解析和订单历史遍历，不绑定代表集 task id。
2. 实现取消订单、修改 pending order 地址、修改支付方式三个可组合 skill flow，并继续统一经过 Guard confirmation。
3. 以 E8 代表集作为验收门槛：目标从 `2/5` 提升到 `5/5` 业务成功，同时要求参数完全匹配和确认后数据库状态变化。
4. rule baseline 达到门槛后，再运行一次真实 LLM 代表集，使用相同 outcome evaluator 比较 planner 能力与成本。

阶段 E 第九轮已经完成：

1. rule planner 新增通用邮箱识别，并扩展 `Your name is ... live in ...` 等姓名+邮编表达；邮箱查询失败时会回退到姓名+邮编，不会把错误文本当作 user id。
2. 账户型请求统一先获取用户详情，再按显式订单号或用户订单历史检查订单；决策逻辑不读取 benchmark task id。
3. 新增 pending order 取消、收货地址修改、支付方式修改三个通用写流程；地址基于当前订单复制未变字段，支付方式从已认证账户按品牌选择，不生成虚假 ID。
4. 技能注册表已加入邮箱认证、地址修改和支付方式修改边界，三个写工具均保留 `requires_confirmation=True`，继续经过 Guard confirmation。
5. 新增认证解析、认证失败回退、订单读取顺序和三个写工具完整参数的单元测试。
6. 真实 tau2 代表集回归达到业务成功 `5/5`、确认门成功 `5/5`、确认后状态验证 `5/5`；严格轨迹匹配 `2/5`、平均步骤 `5.40`、规则运行成本 `0`。
7. 回归证据保存在 `benchmarks/data/simulations/regression-rule-e9-write-workflows/runtime_subset.json`，报告保存在 `docs/smoke/regression-rule-e9-write-workflows.md`。

下一步建议进入阶段 E 第十轮：

1. 使用相同五任务代表集运行一次真实 LLM planner，比较业务结果、恢复路径、步骤数和实际成本。
2. 针对 rule 与 LLM 的差异改进 planner prompt 和 skill routing，但继续禁止任务 ID 特例。
3. 将 `5/5 confirmed_outcome_success` 固化为本地 rule 质量门槛，并为 LLM 设置可接受的成功率和单任务成本预算。

阶段 E 第十轮已经完成：

1. 使用同一五任务代表集运行真实 LLM planner。原 DeepSeek 模型因免费额度耗尽返回 403，未生成伪 artifact；按既定回退策略改用 `qwen3.7-flash`。
2. 未调参 LLM 基线和带 usage 的最终复测均达到 `5/5 confirmed_outcome_success`；最终复测严格轨迹匹配 `2/5`、平均步骤 `5.40`，与 rule 基线相同。
3. `LiteLLMClient` 新增真实 prompt/completion/total token 累计和逐请求 usage ledger；runtime task 和 summary artifact 均持久化这些用量。缺少 usage 时成本保持 `N/A`。
4. 对 `qwen3.7-flash` 按百炼全球部署范围的公开阶梯原价计算 `estimated_list_cost_cny`，逐请求记录模型、档位、单价范围和价格版本，并明确与实际账单成本区分；未知模型继续保存为 `N/A`。
5. 最终 LLM 代表集使用输入 `155,768` tokens、输出 `29,965` tokens，目录价估算总计 `CNY 0.055126`，平均 `CNY 0.011025/任务`。
6. 新增 `scripts/check_runtime_regression.sh`：质量门从逐任务 confirmed-state 结果重新计算，不盲信 summary，并校验 planner 类型；rule 要求 `5/5` confirmed outcome，LLM 额外限制平均目录价估算不超过 `CNY 0.02/任务`，两者均已通过。
7. 没有针对五个代表 task 调整 prompt 或添加 task ID 特例。退货流程虽成功，但触及 10 步预算并发生多种 fallback，是后续优化重点。
8. 对比报告保存于 `docs/smoke/e10-rule-vs-llm-comparison.md`，最终 LLM artifact 保存于 `benchmarks/data/simulations/regression-llm-e10-qwen37-flash-usage/runtime_subset.json`。

下一步建议进入阶段 E 第十一轮：

1. 扩大代表集到每类多个 task，验证当前 `5/5` 不是小样本偶然结果。
2. 优化 LLM 最近消息压缩与工具 schema 提示，优先降低退货任务的重复读取和 token 消耗。
3. 将质量门接入本地统一验收脚本，并让 Dashboard 展示 token 和目录价估算字段。

阶段 E 第十一轮已经完成：

1. 代表集从 5 个扩大到 9 个独立任务，换货、退货、取消和地址修改各覆盖 2 个任务；支付方式修改因 tau2 base split 仅有 task `40`，保留 1 个并明确记录数据集限制。
2. 扩展 rule 基线固定为 `5/9` confirmed outcome，新增任务揭示了身份表达泛化缺口，不再用原 `5/5` 小样本掩盖该问题。
3. LLM planner 上下文去除 assistant 过程叙述和完全重复的工具结果，同时压缩 tool/skill schema；保留最近用户请求和不同工具结果，避免丢失决策状态。
4. 质量门新增 `--required-total-tasks`，可同时约束 artifact 样本量和成功数，防止用缩小样本绕过门禁。
5. 新增 `scripts/validate_local.sh`，统一执行后端测试及已保存的 rule/LLM artifact 门禁，且不会发起付费模型请求。
6. Dashboard 回归汇总和任务详情已显示输入、输出、总 token 与目录价估算；usage 或价格未知时显示 `N/A`。
7. `qwen3.7-flash` 在扩展回归中途耗尽免费额度，未保存不完整 artifact；切换到既定备用 `qwen3.7-flash-2026-07-15` 后完成 9 任务回归，达到 `6/9` confirmed outcome、`3/9` strict exact match、平均 `6.33` 步。
8. 完整 LLM 扩展集使用输入 `243,085`、输出 `79,718`、总计 `322,803` tokens，目录价估算总计 `CNY 0.112391`、平均 `CNY 0.012488/任务`，通过 `CNY 0.02/任务` 成本门。
9. 与 E10 相同五任务相比，压缩后输入 token 从 `155,768` 降到 `136,158`（约 `12.6%`）；输出 token 因新模型决策更冗长从 `29,965` 增至 `41,062`，同任务总 token 仍下降约 `4.6%`。失败集中在 task `2`、`48`、`71`，为下一轮 routing 改进提供了明确样本。

阶段 E 第十二轮已经完成：

1. 对 E11 的 task `2`、`48`、`71` 做定向根因分析和恢复验证，全程不读取 benchmark task id 做决策。
2. 退货目标抽取改为按用户原始表达识别所有订单商品，并排除“仅查询”“暂不处理”等信息型目标；task `48` 因而只退空气净化器，不再误退吸尘器。
3. planner prompt 明确分离 mutation targets 与 information-only items，并要求订单检查完成后继续当前写操作，减少回到旧查询流程的概率。
4. task `2` 的预算从 10 步调整为 12 步；真实 LLM 在第 11 个动作完成三件商品的正确退货并验证数据库状态。
5. E12 rule 基线保持 `5/9 confirmed outcome`，说明本轮未破坏现有规则能力；定向 LLM 回归达到 `2/3 confirmed outcome`，恢复 task `2` 和 `48`。
6. task `71` 仍失败，根因收束为同一请求中的连续多写操作编排，而非单次参数抽取；这是下一阶段的主要实现目标。
7. 定向运行使用输入 `121,934`、输出 `42,632`、总计 `164,566` tokens，目录价估算总计 `CNY 0.058492`、平均 `CNY 0.019497/任务`，通过成本门。
8. `scripts/validate_local.sh` 已纳入 E12 rule 和定向 LLM artifact 门禁，本地验收不会重新调用付费模型。

下一步建议进入阶段 E 第十三轮：实现一个请求内多个写目标的显式执行计划和逐项确认状态机，优先覆盖 task `71`，并复用现有 Guard、MCP 工具和 confirmed-state 验证，不把多写流程硬编码到某个任务。

阶段 E 第十三轮已经完成第一阶段基础实现：

1. `AgentSessionService` 新增原子化 `confirm_pending_and_continue`：快照当前 pending action，确认后以原参数执行，成功后才恢复原始目标；拒绝、执行错误均不会继续。
2. FastAPI 新增 `POST /sessions/{conversation_id}/confirm-and-continue`，可供前端和外部调用方完成逐项确认续跑。
3. 恢复 planner 时会明确携带已完成写操作与原始目标，要求只处理剩余部分，减少重复检索和重复写入。
4. runtime evaluator 新增有界多写循环；只自动确认与 expected write 工具名及完整参数完全一致的动作，确认循环数和 planner 总步数都有上限。
5. `tool_executor.executed` 事件新增 write fingerprint；结果判定会核验全部 expected write fingerprint，task `71` 现在能准确显示 `1/2`，不再只看最后一个写动作。
6. 新增服务、API、多写执行、错误中间参数、动态报告场景等测试；完整后端测试达到 `219 passed`。
7. task `71` 两次真实 LLM 定向验证均正确执行地址修改，但未在预算内提出商品修改。最终复测使用 `95,628` tokens、目录价估算 `CNY 0.037799`，超过既定 `CNY 0.02/任务` 预算，因此停止继续付费重试。
8. E13 证明多写状态机和安全门已工作；剩余问题收束为 planner 在已完成地址修改后仍检查无关订单和已放弃商品，属于目标保持与检索收敛问题。

下一步建议进入阶段 E 第十四轮：为 planner 增加结构化 objective ledger，显式记录已完成目标、剩余目标和已解析实体，使续跑无需从自然语言与长工具历史中重新推断；先用本地固定 LLM 响应测试覆盖，再只对 task `71` 做一次真实验收。

阶段 E 第十四轮已经完成：

1. `CustomerAgentState` 新增结构化 `ObjectiveLedger`，包含原始目标、锁定订单、已检查订单、已解析商品可用变体和已完成写操作。
2. Ledger 完全由 runtime 与真实工具结果更新：失败调用不记录，重复调用按 fingerprint 或实体 ID 去重，LLM 无权自行声明完成状态。
3. 首次 runtime turn 自动初始化原始目标，后续 `confirm-and-continue` 保留同一目标，不会被续跑提示覆盖。
4. 成功写操作会记录工具名、完整参数和 fingerprint；含 `order_id` 的写操作会锁定目标订单，供后续 mutation 使用。
5. planner context 新增紧凑 `OBJECTIVE_LEDGER` JSON，并要求已完成写操作不得重复、锁单后不得遍历无关订单、优先复用已解析商品和订单。
6. task `71` 真实 LLM 验收最终执行 `modify_pending_order_address` 和 `modify_pending_order_items` 两个写操作，均通过独立确认并验证数据库变化，达到 `2/2`、`1/1 confirmed outcome`。
7. 与 E13 最终复测相比，动作数从 `11` 降至 `10`，总 token 从 `95,628` 降至 `79,965`（约下降 `16.4%`），目录价估算从 `CNY 0.037799` 降至 `CNY 0.029161`。
8. 严格轨迹仍为 `0/1`，因为存在额外商品和订单读取；业务结果已正确。多写场景采用独立 `CNY 0.05/任务` 门禁并纳入 `validate_local.sh`，普通单写预算维持 `CNY 0.02/任务`。

下一步建议进入阶段 E 第十五轮：压缩 Objective Ledger 和 planner 工具历史，增加 locked-order 的 runtime 路由约束，减少 task `71` 仍存在的无关读取；随后扩展到第二个多写样本，验证能力不是单样本偶然成功。

阶段 E 第十五轮已经完成：

1. LLM runtime 新增锁单边界：成功写入建立 `locked_order_id` 后，指向其他订单的 `get_order_details` 会改写为锁定订单并记录 `planner.locked_order_redirect`；写工具参数绝不被自动改写。
2. 重复读取恢复逻辑会保留锁定订单读取，不再由 rule fallback 将流程带到其他订单；无锁状态下的订单发现行为保持不变。
3. 新增跨订单读重定向、同订单读保持、跨订单写不改写三类测试，并明确 write `tool_call` 只是由 Guard 接管的待确认提案，planner 不应自行输出确认请求后提前结束。
4. 第一轮真实双样本暴露上述确认契约歧义，`0/2` confirmed outcome，产物作为失败诊断基线保留；修复提示后复验达到 `2/2` business success、`2/2` confirmation gate、`2/2` confirmed outcome。
5. task `71` 用 6 个动作完成地址和商品修改，目录价估算 `CNY 0.012471`；独立 task `96` 用 8 个动作完成商品和地址修改，目录价估算 `CNY 0.025751`。
6. 成功复验共使用输入 `69,673`、输出 `30,360`、总计 `100,033` tokens，目录价估算总计 `CNY 0.038223`、平均 `CNY 0.019111/任务`，通过多写场景 `CNY 0.05/任务` 门禁。
7. 成功 artifact 保存在 `benchmarks/data/simulations/regression-llm-e15-locked-order-generalization-v2/runtime_subset.json`，报告保存在 `docs/smoke/regression-llm-e15-locked-order-generalization-v2.md`，并已纳入 `scripts/validate_local.sh`。
8. 严格轨迹仍为 `0/2`，因为身份认证、必要读取及 task `96` 的一次人工转接提案会被计入动作序列；业务结果门与严格轨迹门继续分开报告。

下一步建议进入阶段 E 第十六轮：将多写目标解析为显式的待办项和依赖关系，减少 task `96` 的人工转接与重复读取，并增加第三类多写组合（例如支付方式加商品修改）验证编排的泛化性。

阶段 E 第十六轮代码实现已经完成，真实终验待模型额度恢复：

1. Planner 决策新增可选 `write_plan`，runtime 仅接受 live catalog 中的写工具，过滤未知/read 工具，规范化重复 ID，并限制为最多 8 项。
2. Ledger 允许相同写工具出现多次；只有真实成功写执行会完成首个匹配目标并记录实际 fingerprint，失败或不匹配不会推进。
3. 订单锁变为当前目标作用域：完成目标后交给下一目标订单，下一目标订单未知时释放，支持跨订单串行写入。
4. 确认续跑使用 `NEXT_WRITE_OBJECTIVE` 和可信 Ledger，不再重复注入已完成写参数；无结构化计划的会话继续保持 E15 兼容行为。
5. Planner 首次遗漏 `write_plan` 时只修复一次；显式空计划不重试。订单读取循环检测改为按 `order_id` 判断，未检查的新订单不会再被 rule fallback 替换。
6. task `59` v1 暴露缺失计划，v2 成功建立两项目标后暴露第二订单读取误判；对应修复均已用本地失败测试复现并通过完整测试。
7. v1 目录价估算 `CNY 0.009410`，v2 为 `CNY 0.012033`，均未达到业务成功，因此只保留为诊断 artifact，不加入 `validate_local.sh`。
8. 修复后的 v3 在首请求被 `qwen3.7-flash-2026-07-15` 和 `qwen3.7-flash` 的共享免费额度 403 阻断，没有生成不完整 artifact，也没有误用多模态模型。

下一步建议：额度恢复或提供新的文本模型后，仅重跑 task `59`；通过 `2/2` confirmed write 与 `CNY 0.05/任务` 门槛后完成 E16，再进入跨订单计划的前端可视化和用户编辑能力。

阶段 E 第十六轮最终验收已经补齐：

1. 默认 Planner 切换到用户提供且仍有免费额度的 `qwen3.8-max`，没有使用语音、图像或视频模型处理文本规划。
2. task `59` v3 成功创建 2 项结构化写计划，独立确认并执行 `cancel_pending_order(#W8268610)` 与 `modify_pending_order_address(#W2702727)`，数据库状态均符合预期，confirmed outcome `1/1`。
3. v3 共 9 个动作；严格轨迹仍为 `0/1`，主要偏差来自 3 次返回 `Order not found` 的读取和额外用户详情读取，属于效率问题而非写入安全问题。
4. 使用输入 `43,649`、输出 `24,004`、总计 `67,653` tokens。新模型尚无项目内可信目录价，因此成本为 `N/A`，不执行虚假 `CNY 0.05` 价格断言。
5. 成功 artifact 为 `benchmarks/data/simulations/regression-llm-e16-structured-write-plan-v3/runtime_subset.json`，报告为 `docs/smoke/regression-llm-e16-structured-write-plan-v3.md`，已加入 E16 离线业务门禁。

下一步建议进入阶段 E 第十七轮：规范化模型生成的订单 ID，并让失败读取优先回到已认证用户的订单列表，从 9 个动作和 3 次错误读取中压缩成本与时延；随后把结构化 write plan 展示到中文前端。

阶段 E 第十七轮已经完成：

1. 新增纯订单 ID canonicalizer，只接受大小写不敏感的 `#?W` 加数字；只读 `get_order_details` 在 schema 校验前规范化并产生审计事件，无法识别的格式不猜测。
2. 所有写工具参数保持原样，确认 fingerprint 与已展示参数不受规范化影响；`write_plan` 中可识别的订单 ID 规范化，错误 ID 变为未知，不建立错误订单锁。
3. Objective Ledger 记录失败订单读取和成功 `get_user_details` 返回的可信订单；planner 获得 `ORDER_LOOKUP_RECOVERY`，排除已检查和失败 ID 后推荐当前计划订单或账户候选。
4. Dashboard 对话测试台新增中文只读写操作计划，展示“当前 / 待处理 / 已完成”、中文工具名、订单 ID 和意图；修复响应式主网格隐式列和宽对比表溢出，1280px 与 390px 均通过浏览器验证。
5. 本地完整测试达到 `262 passed`；E9-E16 离线 artifact 门禁全部通过。质量门新增可选 `--max-failed-order-lookups`，不会改变旧门禁，E17 要求为 `0`。
6. task `59` 真实复验以 6 个动作完成两个写操作并验证数据库变化，confirmed outcome `1/1`，失败订单读取 `0`，达到不超过 7 个动作的目标。
7. E17 使用 `30,187` 输入、`20,563` 输出、`50,750` 总 tokens；较 E16 减少 `16,903` tokens（约 `25.0%`）。`qwen3.8-flash` 缺少可信项目价表，成本继续显示 `N/A`。
8. 成功 artifact 为 `benchmarks/data/simulations/regression-llm-e17-order-id-recovery/runtime_subset.json`，报告为 `docs/smoke/regression-llm-e17-order-id-recovery.md`，已纳入 `scripts/validate_local.sh`。

下一阶段建议进入 E18：把结构化计划、确认记录和最终状态证据整合为单个会话审计视图，并增加可复现的前端交互测试；暂不开放计划编辑，避免用户修改计划与已确认 fingerprint 之间产生新的安全语义。

阶段 E 第十八轮已经完成：

1. 新增独立 `SessionAudit` 只读投影，将 `write_plan`、pending/completed write、Guard 确认事件和工具执行事件按 fingerprint 关联，不修改 runtime 的权威状态。
2. 新增 `GET /sessions/{conversation_id}/audit`，统一返回目标摘要、逐目标确认/执行/状态验证结果和审计时间线；失败执行与用户拒绝不会从审计中消失。
3. Guard 确认事件现在保留原始写参数；Guarded Executor 对写工具采集执行前后数据库哈希，并明确区分 `changed`、`unchanged`、`unavailable` 和 `not_run`。
4. Dashboard 将原写计划区域升级为中文“会话审计”，展示计划状态、确认状态、执行结果、状态证据、参数与 fingerprint；计划仍只读。
5. 浏览器实际验证覆盖待确认、确认后成功执行并改变状态、用户拒绝三条路径；662px 窄视口无横向溢出。
6. 新增 audit 投影、状态证据、API 和静态前端回归测试；本阶段没有调用模型 API。

下一阶段建议进入 E19：在既有 `RetailToolPort` 边界实现真正的 MCP adapter/bridge，先完成 MCP tool discovery、调用、超时和错误归一化，再通过配置在 tau2 与 MCP 后端之间切换；Agent Runtime、Guard 和会话审计保持无感。

阶段 E19-E20（独立客服中心准产品）已经完成：

1. 新增 SQLite 会话、消息、待确认操作与审计持久化，浏览器或 API 重启后可恢复历史与待处理状态，`executing` 操作不会自动重放。
2. 新增版本化 `/api/v1/support` 服务边界和用户安全投影，隔离策略、工具名、原始参数、trace、reward 与 cost。
3. 新增 `/support/` 中文客服中心，覆盖会话历史、身份状态、真实订单卡片、确认/拒绝控件、操作结果、错误恢复和移动端抽屉；根路径默认进入客服中心，`/dashboard/` 保留为工程控制台。
4. `RetailToolPort` 已实现真实 MCP Streamable HTTP 服务端与客户端，启动时校验 16 个工具，调用失败不会静默回退到进程内后端。
5. 新增 Conda 本地一键启动、Dockerfile、Compose、产品栈检查、E2E 恢复测试和无额外 npm 依赖的 UI 合约验证脚本。
6. 真实浏览器已验证身份认证、订单查询、持久化刷新、1440px 桌面和 390px 手机布局；手机视口 `scrollWidth == innerWidth`，历史抽屉和输入区可用。
7. 当前定位为“本地可完整演示和使用的准产品”，约完成目标的 90%。Docker 实机、生产认证/租户、HTTPS、监控备份、并发压测与真实电商系统接入是明确保留的最后 10%。

阶段 E21（本地账户与角色权限）已经完成代码实现：

1. SQLite migration 新增用户、哈希登录会话与认证审计表，并为客服会话增加所有者外键；初始开发人员由 SQL 预置且首次登录必须改密。
2. 密码使用标准库 scrypt 加盐存储，浏览器使用 HttpOnly/SameSite Cookie，数据库只保存 Session token 哈希。
3. 普通用户公开注册后进入独立客服中心；开发人员进入原有完整观测 Dashboard，普通用户不能访问工程页面或工程 API。
4. 现有 Dashboard 新增开发人员管理，可创建、启用和禁用开发人员，同时保留评测、Trace、审计、工具与成本视图。
5. 客服会话按产品登录账户隔离；另一个普通用户和历史无归属会话不会出现在当前用户的客服 API 中。
6. 生产环境仍需补充 OIDC/MFA、找回密码、邮件验证、分布式限流、HTTPS 强制、CSRF 策略和正式安全审查。

阶段 E22（流式交互、权限披露与人工接管）已经完成：

1. Agent Runtime 新增结构化进度事件，客服消息通过 SSE 持续返回接受、工作阶段、业务块、待确认和完成事件；前端显示阶段与耗时，不暴露模型思维链。
2. 客服中心明确披露查询自动执行、写操作逐次确认和人工可接管三类权限；确认只授权当前 fingerprint，参数变化继续走原有 Guard 重新确认。
3. SQLite migration v7 新增持久化人工工单，支持待接入、处理中、已解决和已取消状态；重复申请幂等，重启后可恢复。
4. 工程控制台新增独立“人工接管”页面，支持筛选、查看安全会话摘要、接入、解决和取消，不授予开发人员客户登录会话。
5. 人工接管活跃期间，客户写操作确认统一返回 `409 human_handoff_active`，避免自动系统与人工客服并发修改业务状态。
6. 新增 SSE 分片解析、流式 API、接管服务/API、角色权限、静态页面和真实本地栈验收；完整后端测试及产品验收脚本作为收口门禁。

阶段 E23（会话焦点记忆）已经完成：

1. `ObjectiveLedger` 新增可信 `active_order_id`，只由成功的订单详情工具结果更新，不允许模型自行声明当前订单。
2. Planner 紧凑上下文同时保留最近一条用户消息、最近一条客服回答和去重工具结果，支持解析“取消订单”“就这个”等省略表达。
3. 当焦点订单唯一时，Planner 被约束为继续处理该订单，不再重新枚举无关订单；真正写操作仍必须补齐取消原因等必填参数并经过原有确认门禁。
4. 新增 `#W8770097 → 取消订单` 上下文回归测试；完整后端测试达到 `431 passed`。

阶段 E24（客户会话管理）已经完成：

1. SQLite migration v8 新增客户自定义会话分组、置顶状态和标题来源；每个会话最多属于一个分组。
2. 客服侧栏支持重命名、置顶/取消置顶、移动分组和逻辑删除；删除分组不会删除会话。
3. 新建会话会自动归档同一用户此前所有 0 问题空会话，已有用户问题的会话保持不变。
4. 所有会话与分组 API 均按登录用户隔离，跨用户 ID 统一按未找到处理。
5. 后端完整回归达到 `438 passed`，并扩展客服 UI 自动验收覆盖会话管理生命周期。

阶段 E 的目标是把当前“能查看差异”推进到“能稳定定位为什么 rule 和 LLM 行为不同，并指导下一轮 agent 改进”。
