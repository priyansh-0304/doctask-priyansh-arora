"""Stage 2.5: Entity resolution. Different documents refer to the same
feature by different names. Pure embedding similarity alone isn't
reliable for short, sparse phrases like feature names -- so:
  - high similarity: auto-merge, no LLM call needed
  - low similarity: auto-separate, no LLM call needed
  - ambiguous band: ask the LLM for a recommendation, but treat it as
    exactly that -- a recommendation flagged for human confirmation,
    not a silent final verdict.
"""

import os
import time
import numpy as np
from app.cost_tracker import tracker
from google import genai

EMBED_MODEL = "gemini-embedding-001"
CHAT_MODEL = "gemini-3.5-flash-lite"

UPPER_BOUND = 0.80
LOWER_BOUND = 0.55


class EntityResolver:
    def __init__(self, api_key: str | None = None):
        self.client = genai.Client(api_key=api_key or os.environ["GEMINI_API_KEY"])
        self.canonical_names: list[str] = []
        self.canonical_embeddings: list[np.ndarray] = []
        self._embed_cache: dict[str, np.ndarray] = {}
        self._resolution_cache: dict[str, tuple[str, float | None, str]] = {}
        self.pending_review: list[dict] = []

    def _embed(self, text: str) -> np.ndarray:
        if text in self._embed_cache:
            return self._embed_cache[text]

        start = time.time()
        response = self.client.models.embed_content(model=EMBED_MODEL, contents=text)
        duration = time.time() - start
        tracker.record("resolve_embed", EMBED_MODEL, 0, 0, duration)

        embedding = np.array(response.embeddings[0].values)
        self._embed_cache[text] = embedding
        return embedding

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    def _llm_confirms_same_feature(self, name_a: str, name_b: str) -> bool:
        prompt = (
            f'In casual internal company documents (PRDs, status reports, meeting notes), '
            f'teams often refer to the same feature with different levels of formality -- '
            f'for example a PRD might add a version suffix like "v1" or "Feature" while a '
            f'status report or meeting note drops it and uses a shorter casual name. A version '
            f'suffix like "v1" does NOT by itself imply a genuinely separate, differently-versioned '
            f'entity -- treat it as a formality difference unless there is other evidence of a '
            f'real distinction.\n\n'
            f'Are these two phrases most likely referring to the SAME feature, or genuinely '
            f'DIFFERENT features?\n\n'
            f'A: "{name_a}"\nB: "{name_b}"\n\n'
            f'Answer with exactly one word: SAME or DIFFERENT.'
        )
        start = time.time()
        response = self.client.models.generate_content(model=CHAT_MODEL, contents=prompt)
        duration = time.time() - start

        usage = getattr(response, "usage_metadata", None)
        prompt_tokens = getattr(usage, "prompt_token_count", 0) or 0
        output_tokens = getattr(usage, "candidates_token_count", 0) or 0
        tracker.record("resolve_llm_tiebreak", CHAT_MODEL, prompt_tokens, output_tokens, duration)

        return response.text.strip().upper().startswith("SAME")

    def resolve(self, feature_name: str) -> tuple[str, float | None, str]:
        if feature_name in self._resolution_cache:
            return self._resolution_cache[feature_name]

        embedding = self._embed(feature_name)
        result = None

        if self.canonical_embeddings:
            scores = [self._cosine_similarity(embedding, c) for c in self.canonical_embeddings]
            best_idx = int(np.argmax(scores))
            best_score = scores[best_idx]
            best_name = self.canonical_names[best_idx]

            if best_score >= UPPER_BOUND:
                result = (best_name, best_score, "auto")

            elif best_score >= LOWER_BOUND:
                if self._llm_confirms_same_feature(feature_name, best_name):
                    self.pending_review.append({
                        "mention": feature_name,
                        "matched_to": best_name,
                        "embedding_score": round(best_score, 3),
                    })
                    print(f"    (LLM recommends merge: '{feature_name}' == '{best_name}' "
                          f"[embedding {best_score:.3f}] -- flagged for human confirmation)")
                    result = (best_name, best_score, "llm_recommended")
                else:
                    print(f"    (LLM recommends separate: '{feature_name}' != '{best_name}' "
                          f"[embedding {best_score:.3f}])")
            else:
                print(f"    (no match for '{feature_name}': closest was '{best_name}' "
                      f"at {best_score:.3f}, below {LOWER_BOUND})")

        if result is None:
            self.canonical_names.append(feature_name)
            self.canonical_embeddings.append(embedding)
            result = (feature_name, None, "new")

        self._resolution_cache[feature_name] = result
        return result

    def embed_text(self, text: str) -> np.ndarray:
        """Public wrapper around _embed, for reuse outside entity resolution."""
        return self._embed(text)

    def similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Public wrapper around _cosine_similarity."""
        return self._cosine_similarity(a, b)