from functools import lru_cache
from threading import Lock
from typing import List

from sentence_transformers import CrossEncoder

from app.config import get_settings

# Constructing a CrossEncoder costs ~3s; scoring 20 pairs costs ~90ms. Cache the
# model so it is paid once per process instead of once per call site.
_PREDICT_LOCK = Lock()


@lru_cache(maxsize=4)
def get_cross_encoder(model_name: str) -> CrossEncoder:
    return CrossEncoder(model_name)


def predict_pairs(model: CrossEncoder, pairs: List[tuple]) -> List[float]:
    """Score query/passage pairs. Serialized so worker threads can share one model."""
    if not pairs:
        return []
    with _PREDICT_LOCK:
        scores = model.predict(pairs)
    return [float(s) for s in scores]


class Reranker:
    """Cross-encoder reranking for retrieved manufacturing chunks."""

    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or get_settings().RERANK_MODEL
        self.model = get_cross_encoder(self.model_name)

    def rerank(self, query: str, contexts: List[dict], top_k: int = 5) -> List[dict]:
        if not contexts:
            return []

        scores = predict_pairs(self.model, [(query, c["text"]) for c in contexts])

        ranked = sorted(zip(contexts, scores), key=lambda item: item[1], reverse=True)
        results = []
        for ctx, score in ranked[:top_k]:
            item = dict(ctx)
            item["rerank_score"] = score
            results.append(item)
        return results


@lru_cache(maxsize=1)
def get_reranker() -> Reranker:
    """Process-wide reranker so the API and the evaluator share one loaded model."""
    return Reranker()
