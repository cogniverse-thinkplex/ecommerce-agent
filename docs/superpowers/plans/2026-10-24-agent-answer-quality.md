# Agent Answer Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为客服 Agent 建立稳定、可测试的中文回答质量层。

**Architecture:** LLM Planner 负责决策，回答契约约束自由文本；`response_composer` 负责把可信工具结果转换为客户可读话术；独立质量检查器输出可解释问题标签。全程不增加额外模型调用。

**Tech Stack:** Python 3.12、Pydantic、pytest、现有 FastAPI/Agent runtime

**Spec:** `docs/superpowers/specs/2026-10-24-agent-answer-quality-design.md`

## Global Constraints

- 不暴露工具名、原始异常、内部推理或未验证事实。
- 不新增付费模型调用。
- 所有行为变更先写失败测试。

## Review Focus

- 缺字段或非 JSON 工具结果应优雅降级。
- 多商品、多支付记录和未知状态不能导致异常。
- 写操作尚未确认时不能生成“已完成”。
- 中文文案不得改变订单号、金额和商品事实。
- 质量检查只能标记问题，不能篡改业务事实。

---

### Task 1: 中文回答契约

**Files:**
- Modify: `backend/app/agent/proposal_generator.py`
- Test: `backend/tests/agent/test_proposal_generator.py`

**Interfaces:**
- Produces: `_planner_system_prompt() -> str` 中的客户回答约束。

- [x] 写提示词契约失败测试。
- [x] 运行定向测试确认失败。
- [x] 添加中文、事实、焦点、错误与下一步约束。
- [x] 运行定向测试确认通过。

### Task 2: 工具结果用户化表达

**Files:**
- Modify: `backend/app/agent/response_composer.py`
- Create: `backend/tests/agent/test_response_composer.py`

**Interfaces:**
- Produces: `compose_tool_response(message: ConversationMessage) -> str | None`。

- [x] 为订单、用户、商品、写操作和错误写失败测试。
- [x] 运行测试确认失败。
- [x] 实现状态、金额、商品和安全错误表达。
- [x] 运行测试确认通过。

### Task 3: 回答质量检查

**Files:**
- Create: `backend/app/agent/response_quality.py`
- Create: `backend/tests/agent/test_response_quality.py`

**Interfaces:**
- Produces: `inspect_customer_response(text: str) -> list[ResponseQualityIssue]`。

- [x] 为原始错误、内部工具名、英文状态和无下一步问题写失败测试。
- [x] 运行测试确认失败。
- [x] 实现纯函数检查器和稳定问题代码。
- [x] 运行定向与完整测试。
