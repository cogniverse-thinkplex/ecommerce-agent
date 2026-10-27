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

[返回课程主页](README.md)

