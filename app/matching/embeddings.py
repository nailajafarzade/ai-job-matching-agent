"""Embedding model behind a small interface.

The rest of the code only knows `Embedder`. To use another model, write
another class with the same two members and change one line in config.py.
The real model is loaded ONCE (get_embedder is cached), not on every request.
"""
from functools import lru_cache
from typing import Protocol

import numpy as np

from app.config import EMBEDDING_MODEL


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str]) -> np.ndarray:
        """One row per text. Rows are normalized, so a dot product is cosine similarity."""
        ...


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str = EMBEDDING_MODEL):
        from sentence_transformers import SentenceTransformer  # slow import, so it is inside

        self.name = model_name
        self._model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors = self._model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
        return np.asarray(vectors, dtype=np.float32)


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    """Load the model once. Call this at app start (see app/main.py later)."""
    return SentenceTransformerEmbedder()
