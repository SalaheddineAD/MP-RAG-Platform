"""
RAG Evaluation Pipeline

Reports four independent metrics per golden-set question:

- faithfulness       Are the answer's claims supported by the RETRIEVED CONTEXT?
                     This is the RAGAS/TruLens definition and is what detects
                     hallucination. It never looks at the expected answer.
- answer_correctness Does the answer contain the facts in the EXPECTED ANSWER?
                     This is what detects retrieval gaps.
- answer_relevance   Does the answer actually address the question?
- context_precision  What fraction of retrieved chunks were relevant?

Keeping faithfulness and correctness separate matters: an answer can be fully
grounded in the retrieved context (faithful) while still missing facts that
live in a chunk that was never retrieved (incorrect). Collapsing the two hides
which half of the pipeline is at fault.
"""

import json
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from app.config import get_settings
from app.generation.openai_client import OpenAIGenerator
from app.retrieval.hybrid_search import HybridSearch
from app.retrieval.reranker import Reranker, get_cross_encoder, predict_pairs

# Citations are added by the generator, not drawn from the source text. Their
# chunk numbers would otherwise be scored as ungrounded numeric claims.
_CITATION_RE = re.compile(r"\[Source:[^\]]*\]", re.IGNORECASE)
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_WORD_RE = re.compile(r"[a-z]+")

_NUMBER_WORDS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
    "eleven": "11", "twelve": "12", "twenty": "20", "thirty": "30",
    "forty": "40", "fifty": "50", "hundred": "100", "thousand": "1000",
}

# Surface forms that must compare equal: "80 watt-hours/kilogram" == "80 Wh/kg".
_UNIT_ALIASES = [
    (r"watt[\s-]*hours?\s*/\s*kilograms?", "wh/kg"),
    (r"watt[\s-]*hours?\s+per\s+kilograms?", "wh/kg"),
    (r"watts?\s*/\s*kilograms?", "w/kg"),
    (r"kilowatt[\s-]*hours?", "kwh"),
    (r"miles?\s+per\s+gallon", "mpg"),
    (r"miles?\s+per\s+hour", "mph"),
    (r"newton[\s-]*met(?:er|re)s?", "n-m"),
    (r"percent(?:age)?", "%"),
    (r"degrees?\s*c(?:elsius)?\b", "°c"),
    (r"pounds?\s+per\s+square\s+inch", "psi"),
    (r"dollars?", "$"),
]

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being", "have",
    "has", "had", "do", "does", "did", "will", "would", "could", "should", "may",
    "might", "must", "shall", "can", "to", "of", "in", "for", "on", "with", "at",
    "by", "from", "as", "into", "through", "during", "before", "after", "above",
    "below", "between", "under", "and", "but", "or", "so", "if", "because",
    "although", "while", "where", "when", "that", "which", "who", "whose",
    "what", "this", "these", "those", "it", "its", "they", "them", "their",
    "about", "up", "out", "down", "off", "over", "there", "then", "also", "than",
    "too", "very", "just", "more", "most", "less", "such", "some", "any", "no",
    "not", "only", "own", "same", "each", "all", "both", "per", "source",
    "chunk", "approximately", "roughly", "around", "about",
}


def normalize_text(text: str) -> str:
    """Fold unit spellings, number words, and separators so equal facts compare equal."""
    text = text.lower()
    text = text.replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-")
    for pattern, replacement in _UNIT_ALIASES:
        text = re.sub(pattern, replacement, text)
    # 6,000 -> 6000 so digit extraction sees one number
    text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", text)
    for word, digit in _NUMBER_WORDS.items():
        text = re.sub(rf"\b{word}\b", digit, text)
    return text


def extract_numbers(text: str) -> set:
    """Numeric claims in a passage, normalized so 6.20 and 6.2 match."""
    numbers = set()
    for raw in _NUMBER_RE.findall(normalize_text(text)):
        try:
            numbers.add(f"{float(raw):g}")
        except ValueError:
            continue
    return numbers


def extract_content_words(text: str) -> set:
    return {
        word for word in _WORD_RE.findall(normalize_text(text))
        if len(word) > 2 and word not in _STOPWORDS
    }


def strip_citations(text: str) -> str:
    return _CITATION_RE.sub(" ", text)


def sigmoid(x: float) -> float:
    """Cross-encoders are trained with a logistic loss, so logits calibrate via sigmoid."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    exp_x = math.exp(x)
    return exp_x / (1.0 + exp_x)


@dataclass
class EvalResult:
    question: str
    expected_answer: str
    generated_answer: str
    sources: List[dict]
    faithfulness: float
    answer_correctness: float
    answer_relevance: float
    context_precision: float
    latency_ms: float
    cost_usd: float
    difficulty: str
    failure_reason: Optional[str] = None


class RAGEvaluator:
    """Evaluates retrieval and generation quality against a golden set."""

    def __init__(
        self,
        search_engine: HybridSearch,
        generator: OpenAIGenerator,
        reranker: Optional[Reranker] = None,
    ):
        self.search = search_engine
        self.generator = generator
        self.settings = get_settings()
        # Reuse the caller's loaded reranker; falls back to the shared cache.
        self.reranker = reranker or Reranker()
        self.relevance_model = get_cross_encoder(self.settings.RERANK_MODEL)

    # ---------- Public API ----------

    def evaluate(
        self,
        golden_set_path: str,
        namespace: str = "default",
        use_llm_judge: bool = True
    ) -> Dict:
        """Run the full golden set and return aggregates plus per-query detail."""
        golden = []
        with open(golden_set_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    golden.append(json.loads(line))

        if not golden:
            raise ValueError(f"Golden set is empty: {golden_set_path}")

        wall_start = time.time()
        workers = max(1, min(self.settings.EVAL_CONCURRENCY, len(golden)))
        if workers > 1:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                results = list(pool.map(
                    lambda item: self._evaluate_single(item, namespace, use_llm_judge),
                    golden,
                ))
        else:
            results = [self._evaluate_single(i, namespace, use_llm_judge) for i in golden]
        wall_ms = (time.time() - wall_start) * 1000

        failed_queries = [
            {
                "question": r.question,
                "expected": r.expected_answer,
                "generated": r.generated_answer,
                "faithfulness": r.faithfulness,
                "answer_correctness": r.answer_correctness,
                "relevance": r.answer_relevance,
                "retrieved_sources": [s["source"] for s in r.sources[:3]],
                "reason": r.failure_reason,
            }
            for r in results if r.failure_reason
        ]

        by_difficulty = {}
        for diff in ["easy", "medium", "hard"]:
            subset = [r for r in results if r.difficulty == diff]
            if subset:
                by_difficulty[diff] = {
                    "faithfulness": self._mean(r.faithfulness for r in subset),
                    "answer_correctness": self._mean(r.answer_correctness for r in subset),
                    "relevance": self._mean(r.answer_relevance for r in subset),
                    "precision": self._mean(r.context_precision for r in subset),
                    "count": len(subset)
                }

        all_lat = [r.latency_ms for r in results]
        all_cost = [r.cost_usd for r in results]

        return {
            "total_evaluated": len(results),
            "avg_faithfulness": self._mean(r.faithfulness for r in results),
            "avg_answer_correctness": self._mean(r.answer_correctness for r in results),
            "avg_answer_relevance": self._mean(r.answer_relevance for r in results),
            "avg_context_precision": self._mean(r.context_precision for r in results),
            "avg_latency_ms": round(sum(all_lat) / len(all_lat), 2),
            "p95_latency_ms": round(self._percentile(all_lat, 0.95), 2),
            "wall_clock_ms": round(wall_ms, 2),
            "eval_concurrency": workers,
            "avg_cost_per_query": round(sum(all_cost) / len(all_cost), 6),
            "total_cost_usd": round(sum(all_cost), 6),
            "by_difficulty": by_difficulty,
            "failed_queries": failed_queries,
            "detailed_results": [asdict(r) for r in results]
        }

    # ---------- Per-question evaluation ----------

    def _evaluate_single(
        self,
        item: dict,
        namespace: str,
        use_llm_judge: bool
    ) -> EvalResult:
        start_time = time.time()

        contexts = self.search.hybrid_search(
            item["question"],
            namespace,
            top_k=self.settings.TOP_K_DENSE
        )
        ranked_contexts = self.reranker.rerank(
            item["question"], contexts, top_k=self.settings.TOP_K_RERANK
        )

        gen_result = self.generator.generate(item["question"], ranked_contexts)
        latency = (time.time() - start_time) * 1000

        answer = gen_result["answer"]
        faithfulness = self._calculate_faithfulness(answer, ranked_contexts, use_llm_judge)
        correctness = self._calculate_answer_correctness(
            answer, item["expected_answer"], use_llm_judge
        )
        relevance = self._calculate_relevance(item["question"], answer)
        precision = self._calculate_context_precision(item["question"], ranked_contexts)

        from app.monitoring.cost_tracker import CostTracker
        embed_tokens = sum(len(c["text"].split()) for c in ranked_contexts) + len(item["question"].split())
        total_cost = (
            CostTracker.estimate_embedding_cost(int(embed_tokens * 0.75))
            + CostTracker.estimate_generation_cost(
                gen_result["input_tokens"], gen_result["output_tokens"]
            )
        )

        return EvalResult(
            question=item["question"],
            expected_answer=item["expected_answer"],
            generated_answer=answer,
            sources=[{"source": c["source"], "chunk_index": c.get("chunk_index", 0)} for c in ranked_contexts],
            faithfulness=faithfulness,
            answer_correctness=correctness,
            answer_relevance=relevance,
            context_precision=precision,
            latency_ms=latency,
            cost_usd=total_cost,
            difficulty=item.get("difficulty", "easy"),
            failure_reason=self._classify_failure(faithfulness, correctness, precision)
        )

    def _classify_failure(
        self, faithfulness: float, correctness: float, precision: float
    ) -> Optional[str]:
        """Name which half of the pipeline failed, so the report is actionable."""
        low_faith = faithfulness < self.settings.EVAL_FAITHFULNESS_THRESHOLD
        low_correct = correctness < self.settings.EVAL_CORRECTNESS_THRESHOLD

        if low_faith and low_correct:
            return "Ungrounded and incorrect: likely hallucination"
        if low_faith:
            return "Claims not supported by retrieved context: generation hallucinated"
        if low_correct:
            return "Grounded but missed expected facts: retrieval gap"
        if precision < 0.5:
            return "Answer acceptable but retrieval returned mostly irrelevant chunks"
        return None

    # ---------- Faithfulness: answer vs retrieved context ----------

    def _calculate_faithfulness(
        self,
        generated: str,
        contexts: List[dict],
        use_llm_judge: bool
    ) -> float:
        answer = strip_citations(generated).strip()
        if not answer or not contexts:
            return 0.0

        context_text = "\n\n".join(c["text"] for c in contexts)

        # A number in the answer that appears nowhere in the context is the
        # highest-signal evidence of fabrication in technical documentation.
        numeric = self._numeric_groundedness(answer, context_text)
        if numeric is not None and numeric == 0.0:
            return 0.0

        if use_llm_judge:
            judged = self._judge(
                self._faithfulness_prompt(answer, context_text)
            )
            if judged is not None:
                return round(judged, 3)

        if numeric is not None:
            return round(numeric, 3)
        return round(self._lexical_groundedness(answer, context_text), 3)

    @staticmethod
    def _numeric_groundedness(answer: str, context_text: str) -> Optional[float]:
        """Fraction of the answer's numeric claims that appear in the context."""
        answer_numbers = extract_numbers(answer)
        if not answer_numbers:
            return None
        context_numbers = extract_numbers(context_text)
        grounded = len(answer_numbers & context_numbers)
        return grounded / len(answer_numbers)

    @staticmethod
    def _lexical_groundedness(answer: str, context_text: str) -> float:
        """Fallback when the answer states no numbers and no judge is available."""
        answer_words = extract_content_words(answer)
        if not answer_words:
            return 0.0
        context_words = extract_content_words(context_text)
        return len(answer_words & context_words) / len(answer_words)

    @staticmethod
    def _faithfulness_prompt(answer: str, context_text: str) -> str:
        return f"""You are a strict fact-checker.

Decide whether every factual claim in the ANSWER is supported by the DOCUMENTS.
Judge only support by the DOCUMENTS. Do not reward or penalize style, verbosity,
or wording. An answer that restates the documents in different words is fully
supported.

Score 1.0 if every claim is supported, 0.0 if none are, or the supported fraction
in between.

DOCUMENTS:
{context_text}

ANSWER:
{answer}

Respond with ONLY a number between 0.0 and 1.0."""

    # ---------- Answer correctness: answer vs expected answer ----------

    def _calculate_answer_correctness(
        self,
        generated: str,
        expected: str,
        use_llm_judge: bool
    ) -> float:
        answer = strip_citations(generated).strip()
        if not answer or not expected.strip():
            return 0.0

        if use_llm_judge:
            judged = self._judge(self._correctness_prompt(answer, expected))
            if judged is not None:
                return round(judged, 3)

        # Deterministic fallback: did the answer recover the expected facts?
        expected_numbers = extract_numbers(expected)
        if expected_numbers:
            found = len(expected_numbers & extract_numbers(answer))
            return round(found / len(expected_numbers), 3)

        expected_words = extract_content_words(expected)
        if not expected_words:
            return 0.0
        recall = len(expected_words & extract_content_words(answer)) / len(expected_words)
        return round(recall, 3)

    @staticmethod
    def _correctness_prompt(answer: str, expected: str) -> str:
        return f"""You are grading a factual answer against a reference answer.

Score how much of the REFERENCE's factual content the ANSWER conveys. Numbers,
units, and quantities must match to count as correct, but wording, ordering, and
extra correct detail must NOT be penalized. "32 percent over 5 days" and "32% of
stored energy was lost over five days" are equivalent and score 1.0.

Score 1.0 if every fact in the REFERENCE is present in the ANSWER, 0.0 if none
are, or the fraction conveyed in between.

REFERENCE:
{expected}

ANSWER:
{answer}

Respond with ONLY a number between 0.0 and 1.0."""

    # ---------- Relevance and precision ----------

    def _calculate_relevance(self, question: str, answer: str) -> float:
        """Sigmoid-calibrated cross-encoder score for question/answer relevance."""
        scores = predict_pairs(self.relevance_model, [(question, answer)])
        if not scores:
            return 0.0
        return round(sigmoid(scores[0]), 3)

    def _calculate_context_precision(self, question: str, contexts: List[dict]) -> float:
        """Fraction of retrieved chunks that are relevant to the question."""
        if not contexts:
            return 0.0
        scores = predict_pairs(
            self.relevance_model, [(question, c["text"]) for c in contexts]
        )
        threshold = self.settings.CONTEXT_RELEVANCE_THRESHOLD
        relevant = sum(1 for s in scores if sigmoid(s) >= threshold)
        return round(relevant / len(contexts), 3)

    # ---------- LLM judge ----------

    def _judge(self, prompt: str) -> Optional[float]:
        """Return a 0-1 score from the judge model, or None if it is unavailable."""
        try:
            response = self.generator.client.chat.completions.create(
                model=self.settings.OPENAI_JUDGE_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=10,
                temperature=0.0,
            )
            text = response.choices[0].message.content or ""
        except Exception:
            return None

        match = re.search(r"\d+(?:\.\d+)?", text)
        if not match:
            return None
        return max(0.0, min(1.0, float(match.group())))

    # ---------- Helpers ----------

    @staticmethod
    def _mean(values) -> float:
        values = list(values)
        if not values:
            return 0.0
        return round(sum(values) / len(values), 3)

    @staticmethod
    def _percentile(values: List[float], p: float) -> float:
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
        """Persist results with the config that produced them, for run-to-run comparison."""
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{output_dir}/eval_{timestamp}.json"

        results_with_meta = {
            "timestamp": timestamp,
            "evaluator_version": "2.0.0",
            "config": {
                "chunk_strategy": self.settings.CHUNK_STRATEGY,
                "top_k_dense": self.settings.TOP_K_DENSE,
                "top_k_rerank": self.settings.TOP_K_RERANK,
                "hybrid_alpha": self.settings.HYBRID_ALPHA,
                "embedding_model": self.settings.OPENAI_EMBEDDING_MODEL,
                "embedding_dimensions": self.settings.EMBEDDING_DIMENSIONS,
                "llm_model": self.settings.OPENAI_LLM_MODEL,
                "judge_model": self.settings.OPENAI_JUDGE_MODEL,
                "rerank_model": self.settings.RERANK_MODEL,
            },
            "results": results
        }

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results_with_meta, f, indent=2)

        with open(f"{output_dir}/latest.json", 'w', encoding='utf-8') as f:
            json.dump(results_with_meta, f, indent=2)

        return filename
