# 课程设计参考与延伸阅读

## 为什么这样划分课程

公开搜索很难稳定索引小红书站内个人笔记，因此本课程没有复制无法核验的“学习路线帖”，而是用小红书公开岗位中反复出现的能力要求校准课程覆盖面，再结合本项目代码转化为可实践课时。

小红书公开岗位强调的能力包括：

- Harness Kernel、Agent Loop、上下文组装、记忆、工具调用、审批和遥测；
- Tool、Skill、MCP Server、安全执行和 Agent Identity；
- Prompt、RAG、数据处理、结果解析和链路调试；
- 评测集、Tool 评测、Bad case、任务结果与执行轨迹；
- 智能客服中的意图、多轮状态、规划、工具调用、RAG 和人工闭环。

对应公开页面：

- [Harness Kernel、Context、Memory、Tool 与 MCP](https://job.xiaohongshu.com/campus/position/21899)
- [AI 应用研发：对话、Prompt、Tool、RAG 与评测](https://job.xiaohongshu.com/campus/position/22021)
- [智能客服 Agent：规划、工具、RAG 与评测](https://job.xiaohongshu.com/campus/position/21002)
- [智能客服与问题追踪的全流程实践](https://job.xiaohongshu.com/campus/position/22481)

## GitHub README 结构参考

课程内容和代码完全来自本仓库；以下项目只用于研究 README 的信息组织方式：

- [Dify](https://github.com/langgenius/dify)：首屏价值主张、能力概览、部署入口和生态导航。
- [AutoGen](https://github.com/microsoft/autogen)：分层架构、Quickstart、概念文档和开发者入口。
- [CrewAI](https://github.com/crewAIInc/crewAI)：产品定位、功能列表、示例和社区入口。
- [LangChain](https://github.com/langchain-ai/langchain)：安装、最小示例、组件生态和延伸文档。
- [tau2-bench](https://github.com/sierra-research/tau2-bench)：任务型 Agent 的环境、轨迹和评测方法。

## 建议的延伸顺序

1. 先读本课程并跑通一个真实业务闭环；
2. 再读 MCP 协议和 tau2 evaluator，理解边界与评测；
3. 最后比较 LangChain、AutoGen、CrewAI 等框架如何表达相同的 Runtime 问题；
4. 不要从框架 API 反推架构，应先明确状态、权限、失败模式和验收标准。

## Agent 与推理循环

- [ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629)：理解“推理—行动—观察”循环的经典起点。课程第 01–03 课借鉴其问题定义，但工程实现不会暴露或依赖模型私有思维链。
- [Toolformer](https://arxiv.org/abs/2302.04761)：理解模型如何学习何时调用外部工具。业务系统仍需要独立 schema、权限和执行边界。
- [tau2-bench](https://github.com/sierra-research/tau2-bench)：任务型 Agent 在双控制环境中的评测基准，本项目 Retail 环境和任务语义的来源。

阅读论文时重点区分“研究中的能力证明”和“产品中的可靠性契约”。论文展示模型可以做什么；Harness、Guard 和 Evals 决定系统允许它怎样做。

## Tool 与 MCP

- [Model Context Protocol](https://modelcontextprotocol.io/)：MCP 的协议概念、工具、资源和客户端/服务端边界。
- [JSON Schema](https://json-schema.org/)：理解结构化工具参数的类型、必填项和约束。

课程第 04 课没有把 MCP 描述成权限系统。协议解决互操作，身份、授权、审计和业务合法性仍属于应用层。

## RAG 与检索

- [BGE Embedding](https://github.com/FlagOpen/FlagEmbedding)：BGE 系列模型与检索实践。
- [Sentence Transformers](https://www.sbert.net/)：稠密向量编码与语义检索基础。
- [Reciprocal Rank Fusion](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf)：RRF 的原始方法，解释为何可以融合不同评分尺度的排序器。

建议自己构造精确词、口语改写和多条件政策三个查询，观察 BM25、dense 与 RRF 的差异，而不是只看一个总分。

## 评测与可观测性

- [OpenTelemetry](https://opentelemetry.io/docs/)：Trace、Metric、Log 的通用可观测模型。
- [OWASP Top 10 for LLM Applications](https://owasp.org/www-project-top-10-for-large-language-model-applications/)：Prompt injection、敏感信息披露、过度代理等风险分类。

项目当前使用自己的 Trace 与 telemetry schema，尚未强制依赖 OpenTelemetry；理解通用语义有助于未来接入外部观测平台。

## 如何使用参考资料

1. 先在课程中理解一个工程问题；
2. 到参考资料核对通用定义和研究背景；
3. 回到本项目追踪一个真实请求；
4. 写出当前实现与参考方案的差异；
5. 用测试或评测证明改动，而不是因为某个框架“也这么做”。

[返回课程主页](README.md)

