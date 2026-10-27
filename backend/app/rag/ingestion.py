from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from app.persistence.models import PolicyChunkRecord, PolicyDocumentRecord
from app.persistence.sqlite import SqliteUnitOfWork
from app.rag.models import PolicyIngestionSummary


def tokenize_zh_bigrams(text: str) -> list[str]:
    normalized = text.lower()
    chinese = re.findall(r"[\u4e00-\u9fff]+", normalized)
    tokens = re.findall(r"[a-z]+|\d+", normalized)
    for segment in chinese:
        if len(segment) == 1:
            tokens.append(segment)
        else:
            tokens.extend(segment[index:index + 2] for index in range(len(segment) - 1))
    return list(dict.fromkeys(tokens))


class PolicyIngestionService:
    def __init__(self, unit: SqliteUnitOfWork, corpus_path: Path) -> None:
        self._unit = unit
        self._corpus_path = corpus_path

    def ingest(self) -> PolicyIngestionSummary:
        raw = self._corpus_path.read_bytes()
        corpus_version = hashlib.sha256(raw).hexdigest()[:16]
        entries = json.loads(raw)
        chunk_count = 0
        with self._unit.transaction():
            for item in entries:
                content_hash = hashlib.sha256(item["content"].encode()).hexdigest()
                document = PolicyDocumentRecord(
                    **{key: item.get(key) for key in ("policy_id", "title", "category", "summary", "source_url", "scope", "verified_at")},
                    official_version=item.get("official_version"), content_hash=content_hash,
                )
                self._unit.policy_documents.upsert(document)
                chunks = self._chunks(document.policy_id, item["content"])
                self._unit.policy_chunks.replace_for_policy(document.policy_id, chunks)
                chunk_count += len(chunks)
        return PolicyIngestionSummary(corpus_version=corpus_version, document_count=len(entries), chunk_count=chunk_count)

    def _chunks(self, policy_id: str, content: str) -> list[PolicyChunkRecord]:
        parts = [part.strip() for part in re.split(r"(?<=[。！？])", content) if part.strip()]
        chunks: list[str] = []
        current = ""
        for part in parts:
            if current and len(current) + len(part) > 450:
                chunks.append(current)
                current = ""
            current += part
        if current: chunks.append(current)
        return [PolicyChunkRecord(
            chunk_id=f"{policy_id}-{index}", policy_id=policy_id, sequence=index,
            content=value, token_text=" ".join(tokenize_zh_bigrams(value)),
            content_hash=hashlib.sha256(value.encode()).hexdigest(),
        ) for index, value in enumerate(chunks, start=1)]
