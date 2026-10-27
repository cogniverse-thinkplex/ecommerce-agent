from __future__ import annotations

from app.persistence.sqlite import SqliteUnitOfWork
from app.rag.retrieval import PolicyRetrievalService


class HelpService:
    def __init__(self, unit: SqliteUnitOfWork, retrieval: PolicyRetrievalService) -> None:
        self.unit=unit;self.retrieval=retrieval

    def categories(self) -> list[dict]:
        grouped={}
        for item in self.unit.policy_documents.list_enabled(): grouped[item.category]=grouped.get(item.category,0)+1
        return [{"name":key,"count":grouped[key]} for key in sorted(grouped)]

    def articles(self, category: str | None = None) -> list[dict]:
        return [self._public(item) for item in self.unit.policy_documents.list_enabled(category)]

    def article(self, policy_id: str) -> dict:
        item=self.unit.policy_documents.get(policy_id)
        if item is None or not item.enabled: raise KeyError(policy_id)
        chunks=[chunk.content for chunk in self.unit.policy_chunks.list_enabled() if chunk.policy_id==policy_id]
        return {**self._public(item),"content":"\n\n".join(chunks)}

    def search(self, query: str): return self.retrieval.search(query)

    @staticmethod
    def _public(item) -> dict:
        return {key:getattr(item,key) for key in ("policy_id","title","category","summary","source_url","scope","verified_at")}
