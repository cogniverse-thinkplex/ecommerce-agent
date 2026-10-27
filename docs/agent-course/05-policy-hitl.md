# 第 05 课：Policy Guard、权限与 Human-in-the-loop

## 3 分钟速记

安全边界不能只写在 Prompt 里。模型负责提出动作，确定性 Guard 负责判断能否执行；高风险写操作先生成不可歧义的动作指纹，用户确认后只执行完全相同的动作。

## 学习目标

- 理解为什么 Prompt policy 不能替代代码 policy；
- 理解 action fingerprint 如何防止“确认 A，执行 B”；
- 设计确认、拒绝、过期和重复提交行为。

## 两阶段写操作

```mermaid
sequenceDiagram
    participant P as Planner
    participant G as Guard
    participant U as User
    participant E as Executor
    P->>G: write_tool(arguments)
    G->>G: 规范化参数并计算 fingerprint
    G-->>U: 展示订单、商品、原因和影响
    U->>G: 确认
    G->>G: 比对用户、会话、工具、参数和 fingerprint
    alt 完全一致
        G->>E: execute
    else 已变化或已过期
        G-->>U: 拒绝并重新确认
    end
```

## 权限层次

1. 登录态：请求属于哪个应用账户；
2. 角色：customer 或 developer；
3. Retail 绑定：该账户对应哪个业务用户；
4. 资源所有权：订单是否属于当前业务用户；
5. 状态约束：pending 才能取消，delivered 才能退换；
6. 用户确认：写操作详情是否获得明确同意。

## 代码地图

- [guard.py](../../backend/app/policy/guard.py)：动作分类、fingerprint 和确认判断。
- [guarded_executor.py](../../backend/app/tools/guarded_executor.py)：统一执行入口。
- [retail_identity.py](../../backend/app/auth/retail_identity.py)：身份映射。
- [audit.py](../../backend/app/agent/audit.py)：写操作审计。

## 动手实验

1. 请求取消一个 pending 订单；
2. 在确认前检查订单状态未变化；
3. 回复无关文本，确认不能触发执行；
4. 明确确认，检查 MCP 调用与订单新状态；
5. 重复发送“确认”，验证不会重复取消。

## 验证

```bash
rg -l "fingerprint|requires_confirmation|pending_action" backend/tests
./scripts/test_backend.sh -q
```

## 常见误区

- 用户说“帮我处理”就视为确认；
- 只保存工具名，不保存完整规范化参数；
- Planner 在等待确认期间重新生成了不同参数；
- 对写工具盲目重试；
- 只验证 HTTP 成功，不读取业务状态；
- 登录后取消所有资源级权限校验。

## 课后思考

修改地址时，确认页至少应该显示哪些字段？哪些字段变化会导致旧 fingerprint 失效？

## 核心概念

Policy Guard 是确定性授权层。Prompt 可以告诉模型“写操作前请确认”，但 prompt 不是安全边界：模型可能忽略、误解或被注入。真正的约束必须位于所有工具调用都会经过的执行路径上。

Guard 的典型决策不是布尔值，而是 `allowed / requires_confirmation / denied`。读取本人订单通常允许；取消、退货和修改地址需要确认；访问其他用户或违反业务状态的动作应拒绝。

### Action fingerprint

确认必须绑定“用户看到的那个动作”。系统对规范化后的工具名、参数、会话、用户及必要版本生成 fingerprint。确认请求只授权完全相同的指纹；任何订单号、商品、数量或地址变化都必须重新展示。

```mermaid
sequenceDiagram
    participant P as Planner
    participant G as Guard
    participant U as User
    participant E as Executor
    P->>G: write proposal
    G-->>U: details + fingerprint
    U->>G: confirm(fingerprint)
    G->>G: identity / expiry / equality
    G-->>E: one-time authorization
    E->>E: execute and consume authorization
```

## 本项目中的实现

- `backend/app/policy/guard.py` 分类动作并返回策略决策；
- `backend/app/tools/guarded_executor.py` 把 Guard 放在执行必经路径；
- `backend/app/agent/state.py` 保存 pending proposal 与确认状态；
- `backend/app/support/streaming.py` 向前端发送确认卡片；
- `backend/app/auth/retail_identity.py` 把登录用户绑定到 Retail 身份。

## 执行链路

取消提案进入 Guard 后，系统先验证当前用户、订单归属和动作状态，再生成确认摘要与 fingerprint。用户确认时不重新让模型解释意图，而是提交 fingerprint。Executor 消费一次性授权，执行后清空 pending action，防止刷新页面重复执行。

## 设计取舍

项目采用两阶段写操作，牺牲一次交互换取可理解授权。对于低风险读取自动执行；对于跨用户访问直接拒绝；只有真正的业务写入进入 HITL，避免所有动作都弹窗导致确认疲劳。

人工接管与 HITL 不同：HITL 是用户批准具体动作，handoff 是把整个会话控制权交给人工客服。两者都需要审计，但生命周期和权限不同。

## 失败模式

- 只在 prompt 中要求确认：模型偏离就会绕过；
- 确认按钮不携带 fingerprint：可能确认了被替换的参数；
- 授权没有过期或消费：重复提交导致二次写入；
- 只校验订单存在，不校验归属：形成越权；
- 前端隐藏确认卡片但后端仍 pending：状态不一致。

## 动手实验：证明门禁有效

```bash
./scripts/test_backend.sh -q backend/tests/policy
./scripts/test_backend.sh -q backend/tests/tools/test_guarded_executor.py
```

构造一个取消提案，记录 fingerprint；修改 order_id 后提交旧 fingerprint，预期应拒绝。随后用原参数确认，检查执行只发生一次。这个实验验证的是授权绑定，而不是页面按钮是否可点击。

## 知识检查

为什么“用户刚才说过可以取消”不能替代当前动作确认？因为自然语言授权缺少精确参数、时效和一次性语义，无法抵御上下文漂移与 TOCTOU。

[上一课](04-mcp-tools.md) · [下一课：Context 与 Memory](06-context-memory.md)

