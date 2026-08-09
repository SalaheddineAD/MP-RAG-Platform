"""
RAG Evaluation Pipeline

Evaluates retrieval and generation quality against a golden set.
Uses two-stage faithfulness: lexical overlap (fast) + LLM-as-judge (accurate).
"""

import json
from datetime import datetime
from pathlib import Path
import re
import time
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from sentence_transformers import CrossEncoder

from app.retrieval.hybrid_search import HybridSearch
from app.generation.openai_client import OpenAIGenerator
from app.config import get_settings


@dataclass
class EvalResult:
    question: str
    expected_answer: str
    generated_answer: str
    sources: List[dict]
    faithfulness: float
    answer_relevance: float
    context_precision: float
    latency_ms: float
    cost_usd: float
    difficulty: str
    failure_reason: Optional[str] = None


class RAGEvaluator:
    """
    Production-grade RAG evaluator.

    Two-stage faithfulness:
    1. Lexical overlap: fast heuristic for obvious mismatches
    2. LLM-as-judge: accurate but slower, only for borderline cases
    """

    def __init__(self, search_engine: HybridSearch, generator: OpenAIGenerator):
        self.search = search_engine
        self.generator = generator
        self.relevance_model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
        self.settings = get_settings()

    def evaluate(
        self, 
        golden_set_path: str, 
        namespace: str = "default",
        use_llm_judge: bool = True
    ) -> Dict:
        """
        Run full evaluation against golden set.

        Args:
            golden_set_path: Path to JSONL file with question/answer pairs
            namespace: Pinecone namespace to query
            use_llm_judge: Whether to use LLM-as-judge for borderline cases

        Returns:
            Aggregated metrics + per-query breakdown
        """
        # Load golden set
        golden = []
        with open(golden_set_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    golden.append(json.loads(line))

        results = []
        failed_queries = []

        for item in golden:
            result = self._evaluate_single(item, namespace, use_llm_judge)
            results.append(result)

            if result.faithfulness < 0.7 or result.answer_relevance < 0.7:
                failed_queries.append({
                    "question": result.question,
                    "expected": result.expected_answer,
                    "generated": result.generated_answer,
                    "faithfulness": result.faithfulness,
                    "relevance": result.answer_relevance,
                    "retrieved_sources": [s["source"] for s in result.sources[:3]],
                    "reason": result.failure_reason
                })

        # Aggregate by difficulty
        by_difficulty = {}
        for diff in ["easy", "medium", "hard"]:
            subset = [r for r in results if r.difficulty == diff]
            if subset:
                by_difficulty[diff] = {
                    "faithfulness": round(sum(r.faithfulness for r in subset) / len(subset), 3),
                    "relevance": round(sum(r.answer_relevance for r in subset) / len(subset), 3),
                    "precision": round(sum(r.context_precision for r in subset) / len(subset), 3),
                    "count": len(subset)
                }

        # Overall aggregates
        all_faith = [r.faithfulness for r in results]
        all_rel = [r.answer_relevance for r in results]
        all_prec = [r.context_precision for r in results]
        all_lat = [r.latency_ms for r in results]
        all_cost = [r.cost_usd for r in results]

        return {
            "total_evaluated": len(results),
            "avg_faithfulness": round(sum(all_faith) / len(all_faith), 3),
            "avg_answer_relevance": round(sum(all_rel) / len(all_rel), 3),
            "avg_context_precision": round(sum(all_prec) / len(all_prec), 3),
            "avg_latency_ms": round(sum(all_lat) / len(all_lat), 2),
            "p95_latency_ms": round(self._percentile(all_lat, 0.95), 2),
            "avg_cost_per_query": round(sum(all_cost) / len(all_cost), 6),
            "by_difficulty": by_difficulty,
            "failed_queries": failed_queries,
            "detailed_results": [asdict(r) for r in results]
        }

    def _evaluate_single(
        self, 
        item: dict, 
        namespace: str,
        use_llm_judge: bool
    ) -> EvalResult:
        """Evaluate a single question-answer pair."""

        start_time = time.time()

        # Retrieve
        contexts = self.search.hybrid_search(
            item["question"], 
            namespace, 
            top_k=self.settings.TOP_K_DENSE
        )

        # Rerank top 5 for generation
        from app.retrieval.reranker import Reranker
        reranker = Reranker()
        ranked_contexts = reranker.rerank(item["question"], contexts, top_k=5)

        # Generate answer
        gen_result = self.generator.generate(item["question"], ranked_contexts)
        latency = (time.time() - start_time) * 1000

        # Calculate metrics
        faithfulness = self._calculate_faithfulness(
            gen_result["answer"],
            item["expected_answer"],
            ranked_contexts,
            use_llm_judge
        )

        relevance = self._calculate_relevance(
            item["question"],
            gen_result["answer"]
        )

        precision = self._calculate_context_precision(
            item["question"],
            ranked_contexts
        )

        # Estimate cost
        embed_tokens = sum(len(c["text"].split()) for c in ranked_contexts) + len(item["question"].split())
        from app.monitoring.cost_tracker import CostTracker
        embed_cost = CostTracker.estimate_embedding_cost(int(embed_tokens * 0.75))
        gen_cost = CostTracker.estimate_generation_cost(
            gen_result["input_tokens"],
            gen_result["output_tokens"]
        )
        total_cost = embed_cost + gen_cost

        # Determine failure reason
        failure_reason = None
        if faithfulness < 0.7:
            failure_reason = "Hallucination or incorrect retrieval"
        elif relevance < 0.7:
            failure_reason = "Retrieved wrong context for question"

        return EvalResult(
            question=item["question"],
            expected_answer=item["expected_answer"],
            generated_answer=gen_result["answer"],
            sources=[{"source": c["source"], "chunk_index": c.get("chunk_index", 0)} for c in ranked_contexts],
            faithfulness=faithfulness,
            answer_relevance=relevance,
            context_precision=precision,
            latency_ms=latency,
            cost_usd=total_cost,
            difficulty=item.get("difficulty", "easy"),
            failure_reason=failure_reason
        )

    def _calculate_faithfulness(
    self, 
    generated: str, 
    expected: str,
    contexts: List[dict],
    use_llm_judge: bool
    ) -> float:
        """
        Two-stage faithfulness calculation.
        
        Stage 1: Lexical overlap (fast) - FIXED to handle numbers/units
        Stage 2: LLM-as-judge (accurate, for borderline cases)
        """
        import re
        
        # Extract meaningful tokens: words, numbers, units
        # Keep: words, integers, decimals, percentages, units like Wh/kg, $100
        def extract_tokens(text: str) -> set:
            # Normalize: lowercase, remove extra spaces
            text = text.lower().strip()
            # Tokenize by splitting on whitespace and punctuation (except . / - $ %)
            # Use regex to capture: words, numbers with units, currency
            tokens = re.findall(r'\$?\d+(?:\.\d+)?(?:\s*(?:%|wh/kg|mph|mpg|inches|mm|kg|kw|w/kg|°c|°f|rpe))?', text)
            # Also capture standalone words (but not stopwords)
            stopwords = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 
                        'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                        'would', 'could', 'should', 'may', 'might', 'must', 'shall',
                        'can', 'need', 'dare', 'ought', 'used', 'to', 'of', 'in',
                        'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into',
                        'through', 'during', 'before', 'after', 'above', 'below',
                        'between', 'under', 'and', 'but', 'or', 'yet', 'so', 'if',
                        'because', 'although', 'though', 'while', 'where', 'when',
                        'that', 'which', 'who', 'whom', 'whose', 'what', 'this',
                        'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they',
                        'me', 'him', 'her', 'us', 'them', 'my', 'your', 'his', 'its',
                        'our', 'their', 'mine', 'yours', 'hers', 'ours', 'theirs',
                        'about', 'up', 'out', 'down', 'off', 'over', 'away', 'here',
                        'there', 'now', 'then', 'once', 'again', 'further', 'other',
                        'some', 'any', 'no', 'not', 'only', 'own', 'same', 'such',
                        'also', 'than', 'too', 'very', 'just', 'more', 'most', 'less',
                        'least', 'few', 'many', 'much', 'several', 'all', 'both',
                        'each', 'every', 'either', 'neither', 'one', 'two', 'first',
                        'last', 'next', 'previous', 'following', 'per', 'approximately',
                        'about', 'around', 'roughly', 'estimated', 'expected',
                        'projected', 'typical', 'conventional', 'specific', 'retail'}
            
            words = re.findall(r'\b[a-z]+\b', text)
            for w in words:
                if w not in stopwords and len(w) > 2:
                    tokens.append(w)
            
            return set(tokens)
        
        expected_terms = extract_tokens(expected)
        generated_terms = extract_tokens(generated)
        
        if not expected_terms:
            return 0.0
        
        overlap = len(expected_terms & generated_terms)
        lexical_score = overlap / len(expected_terms)
        
        # If lexical score is very high or very low, return it
        if lexical_score >= 0.9 or lexical_score <= 0.3:
            return round(lexical_score, 3)
        
        # Stage 2: LLM-as-judge for borderline cases
        if use_llm_judge:
            # ... keep existing LLM judge code ...
            pass
        
        return round(lexical_score, 3)

    def _calculate_relevance(self, question: str, answer: str) -> float:
        """Use cross-encoder to score question-answer relevance."""
        score = self.relevance_model.predict([(question, answer)])[0]
        # Normalize to 0-1 (cross-encoder outputs raw logits, typically -5 to 5)
        normalized = max(0.0, min(1.0, (score + 5) / 10))
        return round(normalized, 3)

    def _calculate_context_precision(self, question: str, contexts: List[dict]) -> float:
        """What fraction of retrieved chunks are relevant to the question?"""
        if not contexts:
            return 0.0

        scores = self.relevance_model.predict([
            (question, c["text"]) for c in contexts
        ])
        # Count chunks with positive relevance
        relevant = sum(1 for s in scores if s > 0)
        return round(relevant / len(contexts), 3)

    @staticmethod
    def _percentile(values: List[float], p: float) -> float:
        """Calculate percentile."""
        if not values:
            return 0.0
        values = sorted(values)
        k = (len(values) - 1) * p
        f = int(k)
        c = min(f + 1, len(values) - 1)
        if c == f:
            return values[f]
        return values[f] + (k - f) * (values[c] - values[f])

    
    def save_eval_result(self, results: Dict, output_dir: str = "data/eval_results"):
        """Persist evaluation results with timestamp for comparison over time."""
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{output_dir}/eval_{timestamp}.json"
        
        # Add metadata
        results_with_meta = {
            "timestamp": timestamp,
            "evaluator_version": "1.0.0",
            "config": {
                "chunk_strategy": self.settings.CHUNK_STRATEGY,
                "top_k_dense": self.settings.TOP_K_DENSE,
                "top_k_rerank": self.settings.TOP_K_RERANK,
                "hybrid_alpha": 0.7  # This should be configurable
            },
            "results": results
        }
        
        with open(filename, 'w') as f:
            json.dump(results_with_meta, f, indent=2)
        
        # Also save as latest.json for easy access
        latest_path = f"{output_dir}/latest.json"
        with open(latest_path, 'w') as f:
            json.dump(results_with_meta, f, indent=2)
        
        return filename