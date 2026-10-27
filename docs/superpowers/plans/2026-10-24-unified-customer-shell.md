# Unified Customer Center Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans and TDD.

**Goal:** 统一客户侧功能页导航、视觉基线和页面命名。

**Architecture:** 新建共享 `customer-shell.css` 覆盖各页面重复外壳样式；四个页面使用一致的顶栏标记，各业务页面样式继续负责内部组件。

**Tech Stack:** 原生 HTML/CSS、FastAPI StaticFiles、pytest。

**Spec:** `docs/superpowers/specs/2026-10-24-unified-customer-shell-design.md`

## Global Constraints
- 不改变现有 URL、API、会话和订单助手行为。
- 所有页面入口统一命名为“购物帮助”。
- 不使用红色作为导航或政策页强调色。
- 移动端不得隐藏核心导航入口。

### Task 1: Shared customer shell

**Files:**
- Create: `backend/app/static/customer-shell.css`
- Modify: `backend/app/static/{orders,help,account}/` HTML and account spending HTML
- Test: `backend/tests/api/test_customer_shell_static.py`

- [ ] 添加失败测试，验证统一导航、共享 CSS、无旧文案与移动端入口。
- [ ] 创建共享外壳样式并统一四个页面顶栏。
- [ ] 调整帮助页标题与红色强调，保留业务布局。
- [ ] 运行客户静态页面测试和全量后端测试。
- [ ] 重启并在浏览器验证订单、帮助、消费分析、账户间切换。
