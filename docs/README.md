# 文档导航

公开仓库只保留能帮助读者学习、运行、验证和维护项目的稳定文档。

## 学习课程

- [Agent 工程实战课程](agent-course/README.md)：10 节由 Agent 基础、MCP、HITL、Memory、RAG、评测到生产化的课程。
- [课程参考资料](agent-course/references.md)：课程使用的项目资料与外部参考。

## 运行与维护

- [生产运行手册](operations/production-runbook.md)：启动、健康检查、备份、恢复和生产验收。
- [安全例外说明](operations/security-waivers.md)：已知依赖风险、临时豁免和到期要求。
- [tau2 Retail 基线](baseline/p0_tau2_retail_baseline.md)：基准任务、评测口径与初始结果说明。

## 不随公开仓库发布

以下内容保留在维护者本地工作区，不属于产品文档：

- `docs/smoke/`：按时间生成的临时冒烟与回归运行报告；
- `docs/superpowers/`：开发期间的规格和执行计划；
- `docs/plans/`：文档制作过程计划；
- `docs/validation/`：临时验证产物；
- `docs/final_implementation_roadmap.md`：已经完成的历史实施流水账；
- GitHub 上传检查清单和上传清单模板：发布流程的本地维护资料。

可复现的验证能力仍保留在 `backend/tests/`、`scripts/` 和工程控制台中；清理的是历史输出，不是测试或评测功能。
