from typing import List, Dict

from sentence_transformers import CrossEncoder


class Reranker:
    """Cross-encoder reranking for retrieved manufacturing chunks."""

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model = CrossEncoder(model_name)

    def rerank(self, query: str, contexts: List[dict], top_k: int = 5) -> List[dict]:
        if not contexts:
            return []

        pairs = [(query, c["text"]) for c in contexts]
        scores = self.model.predict(pairs)

        ranked = sorted(
            zip(contexts, scores),
            key=lambda item: float(item[1]),
            reverse=True,
        )
        results = []
        for ctx, score in ranked[:top_k]:
            item = dict(ctx)
            item["score"] = float(score)
            results.append(item)
        return results
