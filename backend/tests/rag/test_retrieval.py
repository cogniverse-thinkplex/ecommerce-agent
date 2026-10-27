from pathlib import Path
import numpy as np

from app.persistence.sqlite import SqliteUnitOfWork
from app.rag.ingestion import PolicyIngestionService
from app.rag.retrieval import PolicyRetrievalService, reciprocal_rank_fusion


class FakeEmbedding:
    model_name = "fake-bge"
    available = True
    def embed(self, texts):
        return np.asarray([[1.0, 0.0] if "退货" in text or "七天" in text else [0.0, 1.0] for text in texts], dtype=np.float32)


class BrokenEmbedding:
    model_name = "missing"
    available = False
    def embed(self, texts): raise RuntimeError("model missing")


def unit(tmp_path):
    value=SqliteUnitOfWork(tmp_path/"retrieval.db");value.initialize()
    corpus=Path(__file__).parents[2]/"app/rag/corpus/taobao_policies.json"
    PolicyIngestionService(value,corpus).ingest();return value


def test_rrf_combines_ranks_without_raw_score_scaling():
    scores=reciprocal_rank_fusion([["a","b"],["b","c"]],k=60)
    assert scores["b"] > scores["a"] > scores["c"]


def test_hybrid_retrieval_returns_citations_and_ranks(tmp_path):
    result=PolicyRetrievalService(unit(tmp_path),FakeEmbedding()).search("七天退货")
    assert result.dense_available and result.hits
    assert result.hits[0].source_url.startswith("https://terms.alicdn.com/")
    assert any(hit.dense_rank for hit in result.hits)
    assert any(hit.bm25_rank for hit in result.hits)


def test_missing_bge_degrades_to_bm25(tmp_path):
    result=PolicyRetrievalService(unit(tmp_path),BrokenEmbedding()).search("预售定金退款")
    assert not result.dense_available and result.degraded_reason
    assert result.hits and result.hits[0].bm25_rank == 1
