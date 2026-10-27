# GitHub 上传版本说明

此目录由 `scripts/build_github_release_bundle.sh` 从本地工作目录生成。

## 已包含

- 本项目后端、前端、测试、脚本和公开文档；
- Docker 与本地运行配置示例；
- tau2-bench 的必要源码、MIT License 和第三方声明；
- 本地演示所需的 tau2 Retail 合成数据。

## 已排除

- `.env`、`.env.production` 和所有本地 API Key；
- SQLite 数据库、WAL/SHM、备份；
- 下载的 BGE 模型缓存；
- Python 虚拟环境与缓存；
- tau2 运行结果、非 Retail 数据域和上游 leaderboard；
- IDE 配置、本机临时文件；
- 原始 DOCX 设计文件，避免暴露文档作者元数据；
- 之前生成的发布目录。

## 第三方来源

本项目使用并修改了 tau2-bench：

- https://github.com/sierra-research/tau2-bench
- License: MIT
- 具体修改见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)

## 上传前

```bash
python scripts/verify_public_bundle.py .
```

该检查不能替代人工审阅。请重点确认 README、历史评测记录和演示数据
都是你愿意公开的内容。

