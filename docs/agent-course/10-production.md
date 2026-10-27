# 第 10 课：生产化、安全、备份与发布

## 3 分钟速记

“能在我的电脑运行”只证明功能链路成立。生产化还需要配置治理、认证授权、限流、健康检查、结构化日志、脱敏、备份恢复、依赖安全和可重复验收。

## 学习目标

- 识别本地准产品和多实例生产系统的差距；
- 理解 health 与 readiness 的区别；
- 掌握备份恢复、安全扫描和发布验收。

## 生产防线

```mermaid
flowchart TB
    Internet[请求] --> Headers[安全 Header / Request ID]
    Headers --> RateLimit[登录限流]
    RateLimit --> Auth[Session + Role]
    Auth --> API[业务 API]
    API --> Guard[Policy Guard]
    Guard --> MCP[MCP Tool]
    API --> Logs[JSON 日志与脱敏]
    API --> DB[(SQLite)]
    DB --> Backup[备份 + 恢复演练]
    API --> Health[/health]
    API --> Ready[/ready]
```

## 当前已实现

- 基于数据库的 customer/developer 账户和 session；
- 首次登录修改默认开发人员密码；
- 登录限流、安全响应头和 Request ID；
- JSON 日志、错误收集与敏感字段脱敏；
- `/health` 与 `/ready`；
- SQLite 备份、恢复和周期备份脚本；
- pip-audit、Bandit 和 secret scan；
- 一键生产验收脚本。

## 代码地图

- [config.py](../../backend/app/operations/config.py)：运行配置。
- [health.py](../../backend/app/operations/health.py)：健康与就绪。
- [http.py](../../backend/app/operations/http.py)：HTTP 运行防线。
- [rate_limit.py](../../backend/app/operations/rate_limit.py)：登录限流。
- [redaction.py](../../backend/app/operations/redaction.py)：敏感信息处理。
- [sqlite_backup.py](../../backend/app/operations/sqlite_backup.py)：备份恢复。
- [production-runbook.md](../operations/production-runbook.md)：运行手册。

## 发布前验收

```bash
./scripts/production_acceptance.sh
```

它应覆盖：配置检查、测试、产品栈、备份恢复、安全扫描和服务状态。验收失败应阻止发布，而不是只记录警告。

## GitHub 发布清单

- 不提交 `.env`、API key、cookie、真实客户数据；
- 不提交 SQLite/WAL/SHM、备份文件和模型缓存；
- 保留 tau2 上游许可证与 attribution；
- 轮换任何曾经暴露的密钥；
- 默认账号只用于本地演示，公开服务必须替换；
- 大型 benchmark 数据使用下载脚本、Release 或对象存储；
- README 清楚区分“当前实现”和“未来路线图”。

## 从 SQLite 演进到多实例

本地单实例继续使用 SQLite 是合理取舍。只有出现多副本并发写、独立 Worker、严格高可用或大规模分析需求时，再迁移 PostgreSQL/队列/集中式可观测平台。不要为“看起来生产化”提前引入无法运维的复杂基础设施。

## 常见误区

- `/health` 永远返回 200，即使数据库和 MCP 已失效；
- 有备份文件但从未做恢复演练；
- 日志记录完整 Prompt、密码和 API key；
- 把开发默认密码用于公网；
- 将本地模型缓存和 700MB 数据直接提交普通 Git；
- 依赖扫描有结果，但没有例外说明和处理责任人。

## 毕业项目

选择一个新的客服能力，例如“修改待处理订单中的商品规格”：

1. 定义 Skill 和 Tool schema；
2. 接入 MCP；
3. 添加身份、状态与确认策略；
4. 完成用户界面；
5. 创建成功、拒绝、越权和失败恢复测试；
6. 添加回归案例和指标；
7. 运行生产验收；
8. 在 README 中只更新已实现内容。

[上一课](09-evaluation-observability.md) · [返回课程主页](README.md) · [返回项目首页](../../README.md)

