from __future__ import annotations

from pydantic import BaseModel, Field


class PolicyIngestionSummary(BaseModel):
    corpus_version: str
    document_count: int
    chunk_count: int


class PolicyHit(BaseModel):
    chunk_id: str
    policy_id: str
    title: str
    category: str
    content: str
    scope: str
    source_url: str
    verified_at: str
    dense_rank: int | None = None
    bm25_rank: int | None = None
    rrf_score: float = 0.0


class PolicySearchResult(BaseModel):
    query: str
    hits: list[PolicyHit] = Field(default_factory=list)
    dense_available: bool
    degraded_reason: str | None = None
