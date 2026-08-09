## Evaluation

We evaluate retrieval and generation quality with a **held-out golden set** of 20 question-answer pairs derived from manufacturing documentation. This is not a toy benchmark — it is the same methodology used in production RAG systems at scale.

### The Golden Set

The golden set (`data/golden_set.jsonl`) contains manually curated questions written **after reading the source documents**, not copied from them. This ensures questions reflect real user intent rather than keyword matching.

Each entry contains:
- `question`: The user query
- `expected_answer`: Ground-truth answer
- `source`: Source document
- `page`: Approximate location (for debugging)
- `difficulty`: `easy` (single fact), `medium` (synthesis), `hard` (cross-document)

**Sample entries:**
```jsonl
{"question": "What is the maximum operating temperature for lithium-ion cells?", "expected_answer": "45°C", "source": "nasa_battery_thermal_mgmt.pdf", "difficulty": "easy"}
{"question": "Which cooling method is recommended for high-discharge scenarios?", "expected_answer": "Liquid cooling with glycol-water mixture", "source": "nasa_battery_thermal_mgmt.pdf", "difficulty": "medium"}
```

### Metrics

| Metric | Definition | Target | Why It Matters |
|--------|-----------|--------|----------------|
| **Faithfulness** | Does the generated answer contain only information from retrieved chunks? | >0.85 | Prevents hallucination. A low score means the LLM is making things up. |
| **Answer Relevance** | Does the answer address the question, not just mention related topics? | >0.90 | Ensures the system is useful, not just "not wrong." |
| **Context Precision** | Of the retrieved chunks, how many were actually relevant? | >0.80 | High precision = lower cost (fewer tokens sent to LLM). |
| **Latency (P95)** | Time for 95% of queries to complete | <1000ms | Users abandon slow systems. Manufacturing engineers need answers on the factory floor. |
| **Cost per Query** | Average Bedrock token cost | <$0.005 | At 1,000 queries/day, a $0.01 difference is $10/day = $3,650/year. |

### How Faithfulness Is Calculated

Faithfulness is computed in two stages:

**1. Lexical Overlap (Fast Heuristic)**
We extract key terms from the expected answer and check if they appear in the generated answer. This catches obvious misses (e.g., expected "45 N·m" but generated "50 N·m").

**2. LLM-as-Judge (Slow but Accurate)**
For answers that pass lexical overlap, we send both the generated answer and the retrieved context to a separate LLM prompt:

```
You are a strict fact-checker. Given the DOCUMENTS and the ANSWER, 
score whether every claim in the ANSWER is supported by the DOCUMENTS.

Score: 1.0 = fully supported, 0.0 = completely unsupported, 0.5 = partially supported.

DOCUMENTS:
{retrieved_chunks}

ANSWER:
{generated_answer}

Score (0.0-1.0):
```

This two-stage approach balances speed (lexical) and accuracy (LLM judge) without calling the LLM for every single evaluation.

### How Answer Relevance Is Calculated

We use a cross-encoder (`ms-marco-MiniLM-L-6-v2`) to score the similarity between the question and the generated answer. This is the same model used for reranking, ensuring consistency between retrieval and evaluation.

A high relevance score means the answer is on-topic. A low score means the RAG retrieved wrong chunks or the LLM went off-script.

### Running Evaluation

```bash
# Run against a specific namespace
curl -X POST "http://localhost:8000/evaluate" \
  -F "namespace=battery_line_1" \
  -F "golden_set=data/golden_set.jsonl"
```

**Response:**
```json
{
  "total_evaluated": 20,
  "avg_faithfulness": 0.87,
  "avg_answer_relevance": 0.91,
  "avg_context_precision": 0.84,
  "avg_latency_ms": 487.2,
  "avg_cost_per_query": 0.0029,
  "by_difficulty": {
    "easy": {"faithfulness": 0.95, "relevance": 0.96, "count": 10},
    "medium": {"faithfulness": 0.82, "relevance": 0.88, "count": 7},
    "hard": {"faithfulness": 0.71, "relevance": 0.79, "count": 3}
  },
  "failed_queries": [
    {
      "question": "What is the first step in emergency shutdown?",
      "expected": "Isolate the battery pack from the load",
      "generated": "The first step is to check the temperature sensors",
      "reason": "Retrieved chunk 3 (maintenance) instead of chunk 7 (emergency procedures)"
    }
  ]
}
```

### Interpreting Results

**Good scores:**
- Faithfulness >0.85: The LLM is not hallucinating.
- Relevance >0.90: The retrieved chunks are answering the question.
- Easy questions >0.90: Your basic retrieval works.
- Hard questions >0.70: Your system can synthesize across chunks.

**Bad scores and what to fix:**
- Low faithfulness + high relevance: The LLM is answering from memory, not from chunks. Tighten the system prompt ("Answer ONLY from the provided documents").
- Low relevance + high faithfulness: The retrieved chunks are wrong. Improve hybrid search (tune alpha), add reranking, or increase top_k.
- Easy questions fail: Your chunking is breaking facts across boundaries. Try semantic chunking or larger chunk_size.
- Hard questions fail: Your system can't connect information across chunks. Add a summary layer or increase context window.

### Continuous Evaluation

In production, evaluation runs on every code change via GitHub Actions. If faithfulness drops below 0.80 on the golden set, the build fails and the PR is blocked.

This prevents "improvements" that accidentally break retrieval quality.
