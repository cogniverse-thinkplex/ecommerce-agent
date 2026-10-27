from pathlib import Path

import numpy as np

from app.persistence.models import PolicyChunkRecord, PolicyDocumentRecord
from app.persistence.sqlite import SqliteUnitOfWork


def test_policy_records_and_float32_embedding_round_trip(tmp_path: Path):
    unit = SqliteUnitOfWork(tmp_path / "rag-repo.db")
    unit.initialize()
    document = PolicyDocumentRecord(
        policy_id="returns", title="七天无理由退货", category="售后",
        summary="商品完好且适用时支持。", source_url="https://terms.alicdn.com/example",
        scope="普通实物商品", verified_at="2026-10-24", content_hash="doc-hash",
    )
    chunk = PolicyChunkRecord(
        chunk_id="returns-1", policy_id="returns", sequence=1,
        content="商品完好且适用时，支持七天无理由退货。",
        token_text="商品 品完 完好 七天 退货", content_hash="chunk-hash",
        embedding=np.asarray([0.1, 0.2, 0.3], dtype=np.float32).tobytes(),
        embedding_model="fake",
    )
    with unit.transaction():
        unit.policy_documents.upsert(document)
        unit.policy_chunks.replace_for_policy(document.policy_id, [chunk])
    loaded = unit.policy_chunks.list_enabled()
    assert unit.policy_documents.get("returns") == document
    assert len(loaded) == 1
    assert np.allclose(np.frombuffer(loaded[0].embedding, dtype=np.float32), [0.1, 0.2, 0.3])
