# Shopping Policy Help Center and Policy RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建接近淘宝真实规则的购物帮助中心，并以本地 BGE + BM25 + RRF 为客服 Agent 提供可追溯政策证据。

**Architecture:** 官方公开协议经人工审核后形成版本化本地语料，SQLite 保存文档、chunk、FTS5 BM25 索引和 float32 embedding。`PolicyRetrievalService` 并行执行 BGE dense 与 BM25，使用 RRF(k=60) 融合；Agent Runtime 在 Planner 前检索并记录事件，客服投影输出安全引用，写操作仍走现有 MCP、Skill、Guard 与 confirmation。

**Tech Stack:** FastAPI、Pydantic、SQLite/FTS5、NumPy、sentence-transformers、`BAAI/bge-small-zh-v1.5`、原生 HTML/CSS/JS、pytest。

**Spec:** `docs/superpowers/specs/2026-10-24-shopping-policy-help-rag-design.md`

## Global Constraints

- Policy RAG 为只读证据层，不得直接执行订单修改或绕过 Guard。
- 客户回答只显示政策摘要、适用条件和官方来源，不显示内部 prompt、embedding 或检索分数。
- 所有政策条目必须有官方 URL、适用范围和最后核验日期。
- 模型未缓存或加载失败时必须明确降级到 BM25，并报告 `dense_available=false`。
- 客户端不能提交模型路径、文档路径、任意用户 ID 或未验证的订单事实。
- 官方文本只保存人工整理摘要，不长篇复制第三方协议。

## Review Focus

- 中文短问句、数字期限、订单状态和特殊品类必须在 BM25 与 dense 任一路可召回。
- 两路候选重复、缺失或分数尺度不同不能破坏 RRF 的确定性排序。
- BGE 权重缺失、离线、模型加载异常时帮助中心仍可使用 BM25。
- 旧会话、Rule planner 和无政策意图的客服请求不能被额外检索污染。
- 检索证据与订单工具结果冲突时，回答必须以当前订单可执行状态为准并说明差异。

---

### Task 1: Versioned policy corpus and persistence

**Files:**
- Create: `backend/app/rag/__init__.py`
- Create: `backend/app/rag/models.py`
- Create: `backend/app/rag/corpus/taobao_policies.json`
- Create: `backend/app/rag/ingestion.py`
- Create: `backend/app/persistence/migrations/014_policy_rag.sql`
- Modify: `backend/app/persistence/models.py`
- Modify: `backend/app/persistence/sqlite.py`
- Create: `backend/tests/rag/test_ingestion.py`
- Create: `backend/tests/persistence/test_policy_rag_repositories.py`

**Interfaces:**
- Produces: `PolicyDocumentRecord`, `PolicyChunkRecord`, repositories `unit.policy_documents`, `unit.policy_chunks`, `unit.policy_ingestion_runs`.
- Produces: `PolicyIngestionService.ingest() -> PolicyIngestionSummary` and deterministic `tokenize_zh_bigrams(text: str) -> list[str]`.

- [ ] 添加 migration/repository 失败测试，覆盖外键、启用状态、FTS5 BM25、embedding 二进制往返和幂等摄取。
- [ ] 编写首批官方来源政策语料，覆盖通用购物、退款取消、七天无理由、质量问题、运费、地址、预售、跨境、免税和争议处理。
- [ ] 实现 migration 014、Pydantic records、SQLite repositories、chunker、中文二元组 tokenizer 和内容哈希版本控制。
- [ ] 运行 `./scripts/test_backend.sh -q backend/tests/rag/test_ingestion.py backend/tests/persistence/test_policy_rag_repositories.py`。

### Task 2: BGE + BM25 + RRF retrieval service

**Files:**
- Create: `backend/app/rag/embedding.py`
- Create: `backend/app/rag/retrieval.py`
- Create: `backend/app/rag/evaluation.py`
- Create: `backend/tests/rag/test_retrieval.py`
- Create: `backend/tests/rag/test_evaluation.py`
- Modify: `benchmarks/pyproject.toml`
- Modify: `benchmarks/uv.lock`
- Modify: `.env.example`
- Create: `scripts/download_policy_embedding_model.sh`

**Interfaces:**
- Consumes: Task 1 repositories and chunk records.
- Produces: `EmbeddingProvider.embed(texts: list[str]) -> numpy.ndarray` and `SentenceTransformerEmbeddingProvider`.
- Produces: `PolicyRetrievalService.search(query: str, top_k: int = 6) -> PolicySearchResult` with per-result `dense_rank`, `bm25_rank`, `rrf_score` and safe citation metadata.
- Produces: `evaluate_policy_retrieval(cases, retriever) -> PolicyRetrievalMetrics`.

- [ ] 先添加 dense cosine、FTS5 BM25、RRF(k=60)、去重、空查询和模型失败降级测试；embedding 使用 deterministic fake。
- [ ] 添加 `sentence-transformers` 与 NumPy 依赖，锁定 `BAAI/bge-small-zh-v1.5` 配置和本地缓存环境变量。
- [ ] 实现懒加载 BGE provider、批量索引、Top 20 双路召回、RRF 融合、Top 6 选择和状态报告。
- [ ] 建立至少 30 条中文政策查询离线集并计算 Recall@5、MRR@10、拒答率和消融结果。
- [ ] 下载模型后运行真实 embedding 冒烟测试；断网缓存与无模型 BM25 降级分别验证。

### Task 3: Customer help center and trusted policy context

**Files:**
- Create: `backend/app/help/service.py`
- Create: `backend/app/api/help.py`
- Create: `backend/app/static/help/index.html`
- Create: `backend/app/static/help/help.css`
- Create: `backend/app/static/help/help.js`
- Modify: `backend/app/api/main.py`
- Modify: customer navigation under `backend/app/static/{support,orders,account}/`
- Create: `backend/tests/api/test_help_api.py`
- Create: `backend/tests/help/test_help_service.py`
- Create: `scripts/validate_help_ui.mjs`

**Interfaces:**
- Consumes: `PolicyRetrievalService.search` and enabled policy repositories.
- Produces: customer routes `/api/v1/help/categories`, `/articles`, `/articles/{policy_id}`, `/search`, `/articles/{policy_id}/assistant`.
- Produces: `/help/` category/search/detail UI and a server-validated `active_policy_id` conversation context.

- [ ] 添加认证、分类、搜索、详情、失效政策 404、助手会话双重归属和无直接写 API 测试。
- [ ] 实现帮助服务与 API，只返回客户安全 DTO；挂载 `/help` 并更新客户侧统一导航。
- [ ] 实现紧凑帮助中心、来源链接、适用条件、最后核验日期、无结果/降级状态和“询问客服”。
- [ ] 验证桌面与移动端搜索、详情、助手预填和登录门禁。

### Task 4: Agent grounding, citations, and observability

**Files:**
- Modify: `backend/app/agent/runtime.py`
- Modify: `backend/app/agent/proposal_generator.py`
- Modify: `backend/app/agent/session_service.py`
- Modify: `backend/app/support/models.py`
- Modify: `backend/app/support/projector.py`
- Modify: `backend/app/support/service.py`
- Modify: `backend/app/api/main.py`
- Create: `backend/tests/agent/test_policy_retrieval_runtime.py`
- Modify: `backend/tests/agent/test_proposal_generator.py`
- Modify: `backend/tests/support/test_projector.py`

**Interfaces:**
- Consumes: `PolicyRetrievalService.search` and trusted `active_policy_id`.
- Produces: `rag.started`, `rag.completed`, `rag.degraded` events and planner context `POLICY_EVIDENCE`.
- Produces: customer-safe `policy_citations` support block.

- [ ] 添加政策意图触发、非政策请求跳过、事件脱敏、Planner evidence、引用投影和模型降级测试。
- [ ] 在 Runtime Planner 前执行检索，将结构化证据写入事件并注入 LLM context；Rule planner 保持确定性行为。
- [ ] 扩展系统提示，要求区分通用政策、特殊例外和当前订单事实，并禁止从 RAG 直接判定写操作成功。
- [ ] 将最终选中来源投影为客户引用 block；保留完整 dense/BM25/RRF 诊断给开发人员。
- [ ] 证明取消、退货和换货仍产生 pending confirmation，RAG 不新增任何写工具。

### Task 5: Engineering debugger, documentation, and release verification

**Files:**
- Create: `backend/app/api/rag.py`
- Modify: `backend/app/api/system.py`
- Modify: `backend/app/static/dashboard/index.html`
- Modify: `backend/app/static/dashboard/app.js`
- Modify: `backend/app/static/dashboard/styles.css`
- Create: `backend/tests/api/test_rag_debug_api.py`
- Modify: `backend/tests/api/test_system_api.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: retrieval status, candidates, fused results and ingestion metadata.
- Produces: developer-only `/api/v1/rag/status`, `/api/v1/rag/debug` and Dashboard “Policy RAG” page.

- [ ] 添加开发人员门禁、客户禁止、状态脱敏和调试结果排序测试。
- [ ] 实现 RAG 状态/调试 API 与独立 Dashboard 子页面，显示模型、语料版本、dense/BM25/RRF 名次、耗时和选中片段。
- [ ] 更新 README：模型下载、离线启动、重建索引、降级含义、来源复核与验收命令。
- [ ] 运行 30 条离线集、帮助中心验收脚本、写操作门禁回归和完整 `./scripts/test_backend.sh -q`。
- [ ] 重启 8020 本地产品，验证 `/health`、`/help/`、客服政策问答引用和 Dashboard RAG 调试页。

