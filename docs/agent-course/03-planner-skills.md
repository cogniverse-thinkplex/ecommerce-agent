# 第 03 课：LLM Planner、Skills 与结构化提案

## 3 分钟速记

Planner 的职责是提出“下一步做什么”，不是直接操作数据库。模型输出必须先解析成受约束的 Tool Proposal，随后仍要经过 schema、身份和 Policy Guard 校验。

## 学习目标

- 理解 LLM Planner 和 Rule Planner 的定位；
- 理解 Skill routing 与工具选择的差别；
- 读懂结构化 proposal、usage 和错误恢复。

## 决策与执行分离

```mermaid
flowchart LR
    Context[受控上下文] --> LLM[LLM Planner]
    LLM --> Parse[结构化解析]
    Parse --> Validate[Schema / Skill 校验]
    Validate --> Proposal[Tool Proposal]
    Proposal --> Guard[Policy Guard]
    Guard --> Executor[Tool Executor]
```

模型可以犯错，但错误应该在 `Parse`、`Validate` 或 `Guard` 被显式识别，而不是直接变成业务副作用。

## Skill 是什么

Skill 把一个业务能力需要的工具、前置条件和上下文提示组织在一起。例如退货 Skill 关心：用户是否已绑定、订单是否属于该用户、订单是否 delivered、商品项是否存在以及是否完成确认。

Skill 不应复制底层工具实现；它提供的是业务路由与约束。

## 代码地图

- [proposal_generator.py](../../backend/app/agent/proposal_generator.py)：LLM/Rule proposal generator。
- [skills.py](../../backend/app/agent/skills.py)：Skill catalog 与选择。
- [order_identity.py](../../backend/app/agent/order_identity.py)：订单实体恢复。
- [response_quality.py](../../backend/app/agent/response_quality.py)：输出质量约束。
- [.env.example](../../.env.example)：默认 LLM 配置。

## 为什么保留 Rule

产品默认是 `llm`。Rule 仍有三个用途：单元测试的确定性夹具、快速定位工具链问题、在模型服务不可用时验证 Guard/MCP 是否正常。Rule 不是产品的主要智能来源。

## 动手实验

对同一个问题分别运行 LLM 与 Rule 回归，比较动作序列、参数、停止原因、Token、成本和业务结果。不要只比较最终回答。

```bash
ECOM_AGENT_PROPOSAL_GENERATOR=llm ./scripts/run_runtime_regression.sh
ECOM_AGENT_PROPOSAL_GENERATOR=rule ./scripts/run_runtime_regression.sh
```

## 验证清单

- 模型返回非 JSON 时能否重试或优雅失败？
- 提案中的工具名是否必须来自 catalog？
- 参数是否经过 schema 校验？
- usage 缺失时是否明确显示不可用，而不是伪造为 0？
- Planner 是否能够利用上轮已经解析的订单？

## 常见误区

- 在 Prompt 里写“请谨慎”就认为安全；
- 让模型自行判断自己是否有权限；
- Tool description 过长且互相重叠，导致路由混乱；
- 用 expected trajectory 强行控制真实 Agent；
- 每次模型调用都丢弃 usage，导致成本台永远为零。

[上一课](02-harness-state-loop.md) · [下一课：MCP 工具层](04-mcp-tools.md)

