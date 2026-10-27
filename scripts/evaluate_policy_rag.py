#!/usr/bin/env python3
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/"backend"),str(ROOT/"benchmarks/src")]

from app.persistence.sqlite import SqliteUnitOfWork
from app.rag.embedding import SentenceTransformerEmbeddingProvider
from app.rag.evaluation import PolicyEvaluationCase, evaluate_policy_retrieval
from app.rag.ingestion import PolicyIngestionService
from app.rag.retrieval import PolicyRetrievalService


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        unit=SqliteUnitOfWork(Path(directory)/"policy-evaluation.db");unit.initialize()
        PolicyIngestionService(unit,ROOT/"backend/app/rag/corpus/taobao_policies.json").ingest()
        cases=[PolicyEvaluationCase.model_validate(item) for item in json.loads((ROOT/"backend/app/rag/corpus/evaluation_queries.json").read_text())]
        metrics=evaluate_policy_retrieval(cases,PolicyRetrievalService(unit,SentenceTransformerEmbeddingProvider()))
        print(metrics.model_dump_json(indent=2))


if __name__=="__main__": main()
