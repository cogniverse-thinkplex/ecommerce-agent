from pydantic import BaseModel, Field


class PolicyEvaluationCase(BaseModel):
    query: str
    expected_policy_ids: list[str] = Field(min_length=1)


class PolicyRetrievalMetrics(BaseModel):
    case_count: int
    recall_at_5: float
    mrr_at_10: float
    miss_rate: float


def evaluate_policy_retrieval(cases: list[PolicyEvaluationCase], retriever) -> PolicyRetrievalMetrics:
    if not cases:
        return PolicyRetrievalMetrics(case_count=0,recall_at_5=0,mrr_at_10=0,miss_rate=0)
    recalled=0; reciprocal=0.0; misses=0
    for case in cases:
        ids=[hit.policy_id for hit in retriever.search(case.query,top_k=10).hits]
        ranks=[index for index,item in enumerate(ids,start=1) if item in case.expected_policy_ids]
        if any(item in case.expected_policy_ids for item in ids[:5]): recalled+=1
        if ranks: reciprocal+=1/min(ranks)
        else: misses+=1
    total=len(cases)
    return PolicyRetrievalMetrics(case_count=total,recall_at_5=recalled/total,mrr_at_10=reciprocal/total,miss_rate=misses/total)
