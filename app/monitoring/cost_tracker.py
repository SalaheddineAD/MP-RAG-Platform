import time
import json
import os
from typing import Dict
from dataclasses import dataclass, field, asdict
from collections import defaultdict
from datetime import datetime


@dataclass
class QueryMetrics:
    timestamp: float = field(default_factory=time.time)
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
    """Track per-query costs with daily budgets."""
    
    EMBED_COST_PER_1K = 0.0001
    CLAUDE_INPUT_PER_1K = 0.003
    CLAUDE_OUTPUT_PER_1K = 0.015
    
    # Hard daily budget
    DAILY_BUDGET_USD = 5.0  # $5/day max
    
    def __init__(self, persist_file: str = "cost_log.jsonl"):
        self.history = []
        self.persist_file = persist_file
        self._load_history()
    
    def _load_history(self):
        """Load previous spend from disk."""
        if os.path.exists(self.persist_file):
            with open(self.persist_file, 'r') as f:
                for line in f:
                    try:
                        data = json.loads(line)
                        self.history.append(QueryMetrics(**data))
                    except:
                        pass
    
    def _save_metric(self, metric: QueryMetrics):
        """Append to persistent log."""
        with open(self.persist_file, 'a') as f:
            f.write(json.dumps(asdict(metric)) + '\n')
    
    def record(self, metrics: QueryMetrics):
        self.history.append(metrics)
        self._save_metric(metrics)
    
    def get_stats(self) -> Dict:
        if not self.history:
            return {}
        
        # Today's spend only
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        today_metrics = [m for m in self.history if m.timestamp >= today_start]
        
        total_cost = sum(m.total_cost for m in self.history)
        today_cost = sum(m.total_cost for m in today_metrics)
        total_queries = len(self.history)
        avg_latency = sum(m.total_latency_ms for m in self.history) / total_queries
        
        return {
            "total_queries": total_queries,
            "total_cost_usd": round(total_cost, 4),
            "today_cost_usd": round(today_cost, 4),
            "daily_budget_usd": self.DAILY_BUDGET_USD,
            "budget_remaining_usd": round(self.DAILY_BUDGET_USD - today_cost, 4),
            "avg_latency_ms": round(avg_latency, 2),
            "avg_cost_per_query": round(total_cost / total_queries, 6),
            "p95_latency_ms": self._percentile([m.total_latency_ms for m in self.history], 0.95),
            "budget_exceeded": today_cost > self.DAILY_BUDGET_USD
        }
    
    def check_budget(self) -> bool:
        """Return True if we can afford another query."""
        stats = self.get_stats()
        return not stats.get("budget_exceeded", False)
    
    @staticmethod
    def _percentile(values, p):
        values = sorted(values)
        k = (len(values) - 1) * p
        f = int(k)
        c = min(f + 1, len(values) - 1)
        return values[f] + (k - f) * (values[c] - values[f]) if c != f else values[f]
    
    @classmethod
    def estimate_embedding_cost(cls, num_tokens: int) -> float:
        return (num_tokens / 1000) * cls.EMBED_COST_PER_1K
    
    @classmethod
    def estimate_generation_cost(cls, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens / 1000) * cls.CLAUDE_INPUT_PER_1K + \
               (output_tokens / 1000) * cls.CLAUDE_OUTPUT_PER_1K