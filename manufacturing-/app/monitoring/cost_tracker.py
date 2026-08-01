import time
from typing import Dict
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class QueryMetrics:
    total_latency_ms: float = 0.0
    embedding_latency_ms: float = 0.0
    retrieval_latency_ms: float = 0.0
    generation_latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    embedding_cost: float = 0.0
    generation_cost: float = 0.0
    strategy: str = "recursive"
    
    @property
    def total_cost(self) -> float:
        return self.embedding_cost + self.generation_cost


class CostTracker:
    """Track per-query costs and latency."""
    
    # Bedrock pricing (approximate, update as needed)
    EMBED_COST_PER_1K = 0.0001  # Titan v2
    CLAUDE_INPUT_PER_1K = 0.003  # Sonnet
    CLAUDE_OUTPUT_PER_1K = 0.015  # Sonnet
    
    def __init__(self):
        self.history = []
    
    def record(self, metrics: QueryMetrics):
        self.history.append(metrics)
    
    def get_stats(self) -> Dict:
        if not self.history:
            return {}
        
        total_cost = sum(m.total_cost for m in self.history)
        total_queries = len(self.history)
        avg_latency = sum(m.total_latency_ms for m in self.history) / total_queries
        
        return {
            "total_queries": total_queries,
            "total_cost_usd": round(total_cost, 4),
            "avg_latency_ms": round(avg_latency, 2),
            "avg_cost_per_query": round(total_cost / total_queries, 6),
            "p95_latency_ms": self._percentile([m.total_latency_ms for m in self.history], 0.95)
        }
    
    @staticmethod
    def _percentile(values, p):
        values = sorted(values)
        k = (len(values) - 1) * p
        f = int(k)
        c = f + 1 if f + 1 < len(values) else f
        return values[f] + (k - f) * (values[c] - values[f]) if c != f else values[f]
    
    @classmethod
    def estimate_embedding_cost(cls, num_tokens: int) -> float:
        return (num_tokens / 1000) * cls.EMBED_COST_PER_1K
    
    @classmethod
    def estimate_generation_cost(cls, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens / 1000) * cls.CLAUDE_INPUT_PER_1K + \
               (output_tokens / 1000) * cls.CLAUDE_OUTPUT_PER_1K