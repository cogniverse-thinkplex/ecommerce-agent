# GitHub 公开发布检查清单

## 可以直接上传

- `backend/app/`、`backend/tests/`：本项目后端、原生 Web 前端和测试；
- `scripts/`：启动、测试、评测、备份和安全脚本；
- `docs/`、`README.md` 和设计文档；
- Dockerfile 与 Compose 示例；
- `.env.example`、`.env.production.example`：仅含空密钥和示例配置；
- `benchmarks/` 的源码、文档和测试，但必须同时保留 `benchmarks/LICENSE` 和根目录 `THIRD_PARTY_NOTICES.md`；
- `benchmarks/data/tau2/domains/retail/`：本地产品需要的合成 Retail fixture。

## 处理后上传

- `benchmarks/`：这是 tau2-bench 的本地 vendored copy，且有少量 usage/cost 修改；必须保留上游 MIT License、来源、下载地址和修改说明；
- 项目自己的代码：当前尚未选择根许可证，公开展示没有问题，但其他人默认没有复制、修改或分发许可。若希望真正开源，应新增根 `LICENSE`；
- `docs/smoke/` 和 `docs/validation/`：可以上传作为质量证据，但发布前应抽查是否包含本机绝对路径、过期模型名或不希望公开的运行输入；
- DOCX 设计文档：内容可公开时可以上传，否则改成发布 PDF/Markdown 摘要。

## 不应上传

- `.env`：当前包含有效的 DashScope API key；
- `data/ecommerce_agent.db*`：账户、密码哈希、会话、反馈、运行状态；
- `data/backups/`：数据库备份；
- `data/models/`：下载的 BGE 模型缓存；
- `benchmarks/.venv/`：1GB 以上的本地虚拟环境；
- `benchmarks/data/simulations/`：本机运行结果；
- Retail 之外的 `benchmarks/data`：上游完整数据和结果约数百 MB，不是本项目运行必需；
- `.idea/`、`.pytest_cache/`、`__pycache__/`、`.DS_Store`、日志和 PID；
- Cookie、访问令牌、私钥以及任何真实客户数据。

## 发布前必须执行

```bash
# 生成额外的脱敏上传目录和压缩包
./scripts/build_github_release_bundle.sh

# 确认忽略规则
git status --short --ignored

# 扫描密钥和常见敏感文件
./scripts/security_scan.sh

# 检查大文件
find . -type f -size +50M -not -path './.git/*'

# 完整验证
./scripts/test_backend.sh -q
```

生成结果位于 `dist/e-commerce-agent-github-<timestamp>/`，同时会产生
对应的 `.tar.gz`。生成器不会修改或删除本机的 `.env`、数据库和模型缓存。

## 建议的首次提交大小

应用代码、文档、测试与 Retail fixture 应保持在普通 Git 可接受范围。
不要提交当前约 2GB 的整个 `benchmarks/` 工作目录；忽略虚拟环境和非
Retail 数据后，仓库会显著缩小。

