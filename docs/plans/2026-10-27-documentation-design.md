# GitHub 首页与 Agent 实战课程设计

## 目标

把项目文档从按开发时间累积的内部记录，重构为两层入口：

1. 根 `README.md` 面向第一次访问 GitHub 的开发者，快速回答“它是什么、能做什么、如何运行、质量如何”。
2. `docs/agent-course/` 面向希望系统学习 Agent 工程的人，按真实执行链路拆成可实践的课程。

## 设计原则

- 只描述仓库中已经实现的能力；未来设想放入路线图，不与现状混写。
- 先给可运行结果，再解释技术原理。
- 所有课程都链接真实代码、给出实验与验证命令。
- 使用 Mermaid 图、能力矩阵和页面地图提升可读性，避免依赖容易过期的装饰图。
- 兼顾产品、Agent、数据、安全、评测和运维，而不是把 Agent 简化为一次 LLM 请求。

## 信息架构

根 README 使用以下顺序：

1. 项目定位与徽章
2. 产品入口与页面地图
3. 核心能力
4. Agent Harness 架构和一次请求的执行链路
5. 快速开始
6. 演示账号与数据说明
7. 质量验证
8. 课程入口
9. 目录结构、限制、路线图、许可和致谢

课程目录分为十课：

1. 从聊天机器人到业务 Agent
2. Harness、状态与 Agent Loop
3. LLM Planner、Skills 与结构化提案
4. MCP 工具层与 Retail 业务
5. Policy Guard、权限和 HITL
6. 上下文、会话记忆与身份边界
7. BGE + BM25 + RRF Policy RAG
8. 客服业务闭环与产品界面
9. 评测、Reflection、回归与可观测性
10. 生产化、安全、备份和发布

## 参考方法

- 借鉴 Dify 的“价值主张—能力—部署”首页节奏。
- 借鉴 AutoGen 的分层架构说明与 Quickstart 导航。
- 借鉴小红书公开 Agent 岗位所强调的 Harness、Loop、Context、Memory、Tool/MCP、审批、遥测、RAG、评测和真实业务闭环，将课程覆盖面与工程能力对齐。

## 验收

- 根 README 不再声称项目使用尚未落地的 React、PostgreSQL、Valkey、Kubernetes 或 LangGraph。
- 课程首页能从零导航到任意一课。
- 每课至少包含目标、架构/流程、代码地图、实践、验证和复盘。
- 所有仓库内相对链接均存在。
- Markdown 代码块和 Mermaid 块闭合。

