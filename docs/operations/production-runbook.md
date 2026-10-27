# 单机生产运行手册

## 部署前提

目标主机需要 Docker Engine 与 Docker Compose v2，并由 HTTPS 反向代理对外提供服务。复制 `.env.production.example` 为 `.env.production`，填入供应商密钥后执行 `chmod 600 .env.production`。仓库、镜像日志和工单中都不得粘贴该文件内容。

## 启动与检查

```bash
docker compose -f docker-compose.yml -f docker-compose.production.yml config
docker compose -f docker-compose.yml -f docker-compose.production.yml up -d --build
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/ready
```

`/health` 仅说明 API 进程存活；`/ready` 同时检查 SQLite 和 MCP 工具目录。发布系统只能在 `/ready` 返回 200 后接入流量。查看请求级结构化日志：

```bash
docker compose logs --tail=200 api
```

使用响应中的 `x-request-id` 关联用户报错、HTTP 日志和工程控制台中的运行问题。

## 数据备份

在线备份使用 SQLite backup API，不直接复制正在写入的 WAL 数据库：

```bash
PYTHONPATH=backend benchmarks/.venv/bin/python scripts/backup_sqlite.py \
  --source data/ecommerce_agent.db --destination data/backups --retain 14
```

每天至少执行一次，并将 `.db` 与同名 `.json` 元数据同步到独立存储。定期在隔离目录做恢复演练：

```bash
PYTHONPATH=backend benchmarks/.venv/bin/python scripts/restore_sqlite.py \
  data/backups/BACKUP.db /tmp/ecommerce-agent-restore.db
```

## 故障恢复与回滚

1. 从负载均衡摘除实例并执行 `docker compose ... stop api`。
2. 对当前数据库再做一次备份；选定已校验的目标备份。
3. 恢复到新路径进行验证，确认后才使用 `--replace` 覆盖正式路径。覆盖时工具会保留 `pre-restore` 安全副本。
4. 重新启动 API，依次检查 `/health`、`/ready`、登录、订单查询和一次只读 Agent 对话。
5. 应用回滚使用上一版镜像，数据库只有在迁移不兼容或数据损坏时才恢复，不能把代码回滚和数据库覆盖绑成一个动作。

## 告警建议

- `/ready` 连续 3 次失败：告警并停止接入新流量。
- HTTP 5xx 比例、LLM/MCP 错误率或 P95 延迟持续升高：在工程控制台按 request ID 排查。
- 磁盘余量低于 20%、最新备份超过 26 小时、恢复演练超过 30 天：运维告警。

机器可读检查可交给 cron、systemd timer 或外部监控执行：

```bash
ECOM_READY_URL=http://127.0.0.1:8000/ready \
ECOM_BACKUP_DIR=data/backups \
PYTHONPATH=backend benchmarks/.venv/bin/python scripts/check_operations.py
```

退出码 `0` 表示服务、备份和磁盘均正常；其他退出码必须触发告警。生产 Compose 中的 `backup` 服务会在启动后立即备份，并按 `ECOM_BACKUP_INTERVAL_SECONDS` 周期继续执行。

## 登录防护与安全扫描

登录入口默认在同一“客户端 IP + 邮箱”组合出现 5 次失败后封禁 15 分钟；邮箱和 IP 仅以 SHA-256 键保存在进程内。成功登录会清除自身失败记录。该实现只适用于单 API 进程，多副本前必须迁移到共享限流存储。

发布前执行：

```bash
UV_BIN=uv scripts/security_scan.sh
```

扫描包括生产依赖漏洞、Bandit 静态检查和秘密模式检查。临时漏洞豁免及到期日记录在 [安全扫描豁免](security-waivers.md)，不得无文档添加 `--ignore-vuln`。

完整验收入口：

```bash
ECOM_READY_URL=http://127.0.0.1:8000/ready \
ECOM_BACKUP_DIR=data/backups \
UV_BIN=uv scripts/production_acceptance.sh
```

## 当前容量边界

该配置是单机 SQLite 基线，只允许一个 API 写实例。需要多副本、跨机房高可用或显著并发增长时，再进行 PostgreSQL、共享缓存和任务队列迁移。

