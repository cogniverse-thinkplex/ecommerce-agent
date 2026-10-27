from app.agent.runtime import BaselineAgentRuntime
from app.agent.state import CustomerAgentState
from app.rag.models import PolicyHit, PolicySearchResult
from app.tools.guarded_executor import GuardedRetailToolExecutor
from app.tools.retail_port import RetailToolDefinition, ToolBackendInfo


class EmptyPort:
    @property
    def backend(self): return ToolBackendInfo(kind="fake", name="fake", managed_by_mcp=True)
    @property
    def policy(self): return ""
    def list_tools(self) -> list[RetailToolDefinition]: return []


class Retriever:
    def __init__(self, dense_available=True):
        self.queries=[]; self.dense_available=dense_available
    def search(self, query, top_k=6):
        self.queries.append(query)
        return PolicySearchResult(query=query, dense_available=self.dense_available, degraded_reason=None if self.dense_available else "model_not_available", hits=[PolicyHit(chunk_id="seven-day-return:0", policy_id="seven-day-return", title="七天无理由退货", category="退款与售后", content="符合条件的商品可在签收后七日内申请退货。", scope="普通实物商品，特殊品类除外", source_url="https://terms.alicdn.com/example", verified_at="2026-10-24", dense_rank=1 if self.dense_available else None, bm25_rank=1, rrf_score=0.03)])


def test_policy_intent_retrieves_and_records_safe_evidence():
    retriever=Retriever()
    runtime=BaselineAgentRuntime(GuardedRetailToolExecutor(EmptyPort()), None, policy_retriever=retriever)
    result=runtime.run_until_blocked(CustomerAgentState(conversation_id="c1"), "七天无理由退货有什么条件？")
    assert retriever.queries == ["七天无理由退货有什么条件？"]
    completed=next(event for event in result.state.events if event.event_type=="rag.completed")
    assert completed.payload["hits"][0]["policy_id"]=="seven-day-return"
    assert "embedding" not in str(completed.payload).lower()


def test_non_policy_request_skips_retrieval_and_degradation_is_explicit():
    retriever=Retriever(dense_available=False)
    runtime=BaselineAgentRuntime(GuardedRetailToolExecutor(EmptyPort()), None, policy_retriever=retriever)
    untouched=runtime.run_step(CustomerAgentState(conversation_id="c1"), "你好")
    assert retriever.queries == [] and not untouched.state.events
    degraded=runtime.run_step(CustomerAgentState(conversation_id="c2"), "退货政策是什么？")
    assert any(event.event_type=="rag.degraded" for event in degraded.state.events)
