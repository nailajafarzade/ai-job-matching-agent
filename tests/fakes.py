"""A small fake embedder for tests: word overlap, no model download.

It is not smart. It only makes similarity high for texts with shared
words, so tests are fast and give the same result every time.
"""
import re
import zlib

import numpy as np

DIM = 512


class HashingEmbedder:
    name = "hashing-test-embedder"

    def __init__(self):
        self.calls = 0  # number of embed() calls, to prove the matcher does not embed rejected jobs

    def embed(self, texts: list[str]) -> np.ndarray:
        self.calls += 1
        out = np.zeros((len(texts), DIM), dtype=np.float32)
        for i, text in enumerate(texts):
            for word in re.findall(r"[a-z0-9+#.]+", text.lower()):
                out[i, zlib.crc32(word.encode()) % DIM] += 1.0
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return out / norms
