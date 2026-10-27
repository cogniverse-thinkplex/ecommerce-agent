# Frontend

本目录是项目的独立 Web 前端。当前采用原生 HTML、CSS 和 ES Modules，
不需要 Node 构建步骤，由 FastAPI 以静态文件方式提供。

## 页面模块

| 目录 | URL | 用途 |
| --- | --- | --- |
| `auth/` | `/login/`、`/register/` | 登录、注册和密码修改 |
| `support/` | `/support/` | 在线客服、会话管理、反馈和人工接管 |
| `orders/` | `/orders/` | 订单中心 |
| `account/` | `/account/` | 个人资料、地址簿和消费分析 |
| `help/` | `/help/` | 购物政策与 Policy RAG |
| `dashboard/` | `/dashboard/` | 工程观测和回归控制台 |
| `shared/` | 根级静态 URL | 客户侧公共导航、布局和样式 |

## 架构边界

- 前端只通过 HTTP/SSE API 访问业务能力，不直接读取 SQLite 或 tau2 数据。
- URL 路由和静态挂载位于 `backend/app/api/main.py`。
- 默认静态根目录是本目录；部署时可通过 `ECOM_FRONTEND_DIR` 覆盖。
- 页面验证脚本位于根目录 `scripts/validate_*_ui.mjs`。

## 验证

```bash
node scripts/validate_support_ui.mjs
node scripts/validate_orders_ui.mjs
node scripts/validate_help_ui.mjs
node scripts/validate_observability_ui.mjs
```

