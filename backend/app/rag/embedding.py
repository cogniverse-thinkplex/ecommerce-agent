from __future__ import annotations

import os
import numpy as np


class SentenceTransformerEmbeddingProvider:
    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or os.getenv("ECOM_POLICY_EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
        self.cache_folder = os.getenv("ECOM_POLICY_MODEL_CACHE", "data/models")
        self._model = None
        self._error: str | None = None

    @property
    def available(self) -> bool:
        if self._model is not None: return True
        if self._error is not None: return False
        try: self._load()
        except Exception as exc: self._error = type(exc).__name__
        return self._model is not None

    def _load(self):
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(
            self.model_name,
            cache_folder=self.cache_folder,
            local_files_only=os.getenv("ECOM_POLICY_MODEL_LOCAL_ONLY", "true").lower() == "true",
        )

    def embed(self, texts: list[str]) -> np.ndarray:
        if not self.available: raise RuntimeError(self._error or "embedding model unavailable")
        return np.asarray(self._model.encode(texts, normalize_embeddings=True), dtype=np.float32)
