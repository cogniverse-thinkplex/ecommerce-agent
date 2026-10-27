# 客户界面精简与美化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 精简并美化客服中心与账户资料页。

**Architecture:** 保持现有原生 ES Modules 和 FastAPI 静态资源结构，仅调整客户前端 DOM、样式和交互。所有业务能力继续调用既有 API。

**Tech Stack:** HTML、CSS、原生 JavaScript、pytest。

**Spec:** `docs/superpowers/specs/2026-10-23-customer-ui-polish-design.md`

## Global Constraints

- 不新增虚假设置或业务写入捷径。
- 不改变后端业务接口。
- 桌面和移动端都必须可用。

### Task 1: 客服中心精简

- [x] 先写静态失败测试，锁定权限条删除、顶栏转人工和快捷问题。
- [x] 实现客服 HTML、空状态交互与视觉样式。
- [x] 运行客服静态测试。

### Task 2: 账户中心美化

- [x] 先写静态失败测试，锁定账户信息、安全设置和地址说明。
- [x] 实现账户页面结构与响应式样式。
- [x] 运行认证与静态测试。

### Task 3: 完整验收

- [x] 运行完整后端测试与 JavaScript 语法检查。
- [x] 重启 8020，执行产品栈和浏览器验收。

### Task 4: 账户地址管理

- [x] 为当前登录客户增加默认地址读取与更新 API，不接受客户端传入用户 ID。
- [x] 将默认地址编辑表单加入账户中心，移除跳转客服修改入口。
- [x] 验证真实零售地址读取、完整测试与产品栈。
