from app.rag.evaluation import PolicyEvaluationCase, evaluate_policy_retrieval
from app.rag.models import PolicyHit, PolicySearchResult


class Retriever:
    def search(self, query, top_k=10):
        ids=["other","target"] if query=="hit" else ["other"]
        return PolicySearchResult(query=query,dense_available=True,hits=[PolicyHit(chunk_id=f"{item}:0",policy_id=item,title=item,category="c",content="x",scope="x",source_url="https://example.com",verified_at="2026-10-24") for item in ids])


def test_evaluation_computes_recall_mrr_and_abstention():
    metrics=evaluate_policy_retrieval([PolicyEvaluationCase(query="hit",expected_policy_ids=["target"]),PolicyEvaluationCase(query="miss",expected_policy_ids=["target"])],Retriever())
    assert metrics.case_count==2 and metrics.recall_at_5==0.5
    assert metrics.mrr_at_10==0.25 and metrics.miss_rate==0.5
