# A+C Authentication Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将三个认证页面统一为极简、电商化、可访问且响应式的产品界面。

**Architecture:** 保留原生静态 HTML/CSS/JS 与现有认证 API。三个页面共享 `auth.css` 和 `auth.js`，本地履约场景图片作为渐进增强视觉，后端继续负责角色路由。

**Tech Stack:** HTML5、CSS、原生 JavaScript、FastAPI 静态资源、pytest、Playwright 验证脚本。

**Spec:** `docs/superpowers/specs/2026-10-23-auth-a-c-redesign-design.md`

## Global Constraints

- 不改变认证 API、Cookie、安全模型和角色跳转。
- 不展示内部角色、工程控制台或分流说明。
- 不新增前端框架和远程运行时依赖。
- 项目引用的视觉资源必须保存在仓库内。

## Review Focus

- 图片加载失败时表单仍完整可用。
- 320px 宽度下字段、按钮和链接不溢出。
- 密码显隐按钮不提交表单并同步可访问名称。
- 请求失败后按钮恢复，错误信息可被辅助技术读取。
- 注册与改密的密码确认逻辑保持不变。

---

### Task 1: 固化认证页面契约

**Files:**
- Modify: `backend/tests/api/test_auth_static.py`

**Interfaces:**
- Consumes: 三个公开认证页面及 `/auth/auth.js`、`/auth/auth.css`
- Produces: 页面文案、安全和交互结构回归断言

- [x] 增加内部角色文案已移除、视觉资源、密码切换按钮与提交状态文案断言。
- [x] 运行认证静态页测试并确认新断言先失败。

### Task 2: 统一认证页面与视觉资源

**Files:**
- Create: `backend/app/static/auth/auth-fulfillment.webp`
- Modify: `backend/app/static/auth/login.html`
- Modify: `backend/app/static/auth/register.html`
- Modify: `backend/app/static/auth/change-password.html`
- Modify: `backend/app/static/auth/auth.css`

**Interfaces:**
- Consumes: 既有表单字段名称、元素 ID 和认证接口
- Produces: 共享 `.auth-shell` 页面结构与 `[data-password-toggle]` 控件

- [x] 添加不含文字和商标的本地电商履约场景图片。
- [x] 重写三个页面的语义结构与客户可见文案。
- [x] 实现桌面双栏、移动单栏、焦点、错误和降级样式。
- [x] 运行认证静态页测试并确认通过。

### Task 3: 完善认证交互并验证

**Files:**
- Modify: `backend/app/static/auth/auth.js`
- Create: `scripts/validate_auth_ui.mjs`

**Interfaces:**
- Consumes: `[data-password-toggle]`、提交按钮的 `[data-label]` 与 `[data-pending-label]`
- Produces: 密码显隐、提交中状态和浏览器级视觉验收

- [x] 实现密码显隐与提交状态恢复，不改变现有请求载荷。
- [x] 添加桌面和移动视口浏览器断言及截图验证。
- [x] 运行定向测试、浏览器验证和完整测试套件。

