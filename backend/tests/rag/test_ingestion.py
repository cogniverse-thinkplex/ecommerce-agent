from pathlib import Path

from app.persistence.sqlite import SqliteUnitOfWork
from app.rag.ingestion import PolicyIngestionService, tokenize_zh_bigrams


def test_tokenizer_keeps_numbers_words_and_chinese_bigrams():
    tokens = tokenize_zh_bigrams("七天无理由退货 pending 7天")
    assert "七天" in tokens and "退货" in tokens and "pending" in tokens and "7" in tokens


def test_corpus_ingestion_is_idempotent_and_searchable(tmp_path: Path):
    unit = SqliteUnitOfWork(tmp_path / "rag.db")
    unit.initialize()
    corpus = Path(__file__).parents[2] / "app/rag/corpus/taobao_policies.json"
    first = PolicyIngestionService(unit, corpus).ingest()
    second = PolicyIngestionService(unit, corpus).ingest()
    assert first.document_count >= 8 and first.chunk_count >= first.document_count
    assert second.corpus_version == first.corpus_version
    assert len(unit.policy_documents.list_enabled()) == first.document_count
    assert unit.policy_chunks.search_bm25(tokenize_zh_bigrams("七天退货"), limit=5)
