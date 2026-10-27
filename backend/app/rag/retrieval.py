from __future__ import annotations

from collections import defaultdict
import numpy as np

from app.persistence.sqlite import SqliteUnitOfWork
from app.rag.ingestion import tokenize_zh_bigrams
from app.rag.models import PolicyHit, PolicySearchResult


def reciprocal_rank_fusion(rankings: list[list[str]], k: int = 60) -> dict[str, float]:
    scores: dict[str, float] = defaultdict(float)
    for ranking in rankings:
        for rank, item_id in enumerate(ranking, start=1): scores[item_id] += 1.0 / (k + rank)
    return dict(scores)


class PolicyRetrievalService:
    def __init__(self, unit: SqliteUnitOfWork, embedding_provider) -> None:
        self._unit = unit
        self._embedding = embedding_provider

    @property
    def model_name(self) -> str:
        return self._embedding.model_name

    @property
    def dense_available(self) -> bool:
        return self._embedding.available

    def search(self, query: str, top_k: int = 6) -> PolicySearchResult:
        query=query.strip()
        if not query: return PolicySearchResult(query=query,dense_available=False,degraded_reason="empty_query")
        bm25_rows=self._unit.policy_chunks.search_bm25(tokenize_zh_bigrams(query),limit=20)
        bm25_ids=[chunk.chunk_id for chunk,_ in bm25_rows]
        chunks={chunk.chunk_id:chunk for chunk in self._unit.policy_chunks.list_enabled()}
        dense_ids=[]; dense_available=False; degraded_reason=None
        try:
            if not self._embedding.available: raise RuntimeError("embedding model unavailable")
            missing=[chunk for chunk in chunks.values() if chunk.embedding is None or chunk.embedding_model!=self._embedding.model_name]
            if missing:
                vectors=self._embedding.embed([chunk.content for chunk in missing])
                with self._unit.transaction():
                    for chunk,vector in zip(missing,vectors):
                        self._unit.policy_chunks.update_embedding(chunk.chunk_id,np.asarray(vector,dtype=np.float32).tobytes(),self._embedding.model_name)
                chunks={chunk.chunk_id:chunk for chunk in self._unit.policy_chunks.list_enabled()}
            query_vector=self._normalize(self._embedding.embed([query])[0])
            scored=[]
            for chunk in chunks.values():
                vector=np.frombuffer(chunk.embedding,dtype=np.float32)
                scored.append((chunk.chunk_id,float(np.dot(query_vector,self._normalize(vector)))))
            dense_ids=[chunk_id for chunk_id,_ in sorted(scored,key=lambda item:(-item[1],item[0]))[:20]]
            dense_available=True
        except Exception as exc:
            degraded_reason=f"{type(exc).__name__}: embedding unavailable"
        scores=reciprocal_rank_fusion([dense_ids,bm25_ids])
        ordered=sorted(scores,key=lambda item:(-scores[item],item))[:top_k]
        dense_rank={value:index for index,value in enumerate(dense_ids,start=1)}
        bm25_rank={value:index for index,value in enumerate(bm25_ids,start=1)}
        hits=[]
        for chunk_id in ordered:
            chunk=chunks[chunk_id];document=self._unit.policy_documents.get(chunk.policy_id)
            if document is None: continue
            hits.append(PolicyHit(chunk_id=chunk.chunk_id,policy_id=document.policy_id,title=document.title,
                category=document.category,content=chunk.content,scope=document.scope,source_url=document.source_url,
                verified_at=document.verified_at,dense_rank=dense_rank.get(chunk_id),bm25_rank=bm25_rank.get(chunk_id),rrf_score=scores[chunk_id]))
        return PolicySearchResult(query=query,hits=hits,dense_available=dense_available,degraded_reason=degraded_reason)

    @staticmethod
    def _normalize(vector: np.ndarray) -> np.ndarray:
        norm=float(np.linalg.norm(vector))
        return vector/norm if norm else vector
