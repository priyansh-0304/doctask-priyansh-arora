"""Test doubles. FakeResolver lets tests control exact similarity scores
between specific strings, without touching the real embedding API."""

import numpy as np


class FakeResolver:
    """embed_text returns a hand-assigned vector per input string;
    similarity is real cosine math on those vectors. Configure exact
    test scenarios by choosing vectors that produce the score you want."""

    def __init__(self, vectors: dict[str, list[float]]):
        self._vectors = {k: np.array(v) for k, v in vectors.items()}

    def embed_text(self, text: str) -> np.ndarray:
        if text not in self._vectors:
            raise KeyError(f"FakeResolver has no vector configured for: '{text}'")
        return self._vectors[text]

    def similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))