# Latency and Faithfulness Improvements

This document records the changes made on `feature/improve-latency-faithfulness`,
why each one was made, and how each was verified.

The work started from a golden-set evaluation run (28 questions, namespace
`battery_line_1`) that reported:

| Metric | Value |
| --- | --- |
| Average faithfulness | 0.750 |
| Average answer relevance | 1.000 (all 28 queries) |
| Average context precision | 0.757 |
| Average latency | 5,758 ms |
| p95 latency | 7,443 ms |
| Flagged failures | 11 of 28 |

Reading the 11 flagged failures against the source document showed that **8 of
them contained factually correct answers**. That reframed the problem: the
largest single defect was in the measurement, not the pipeline.

---

## 1. The reranker was reloaded once per question

**Problem.** `RAGEvaluator._evaluate_single` contained:

```python
from app.retrieval.reranker import Reranker
reranker = Reranker()
ranked_contexts = reranker.rerank(...)
```

`Reranker.__init__` constructs a `CrossEncoder`, which loads model weights from
disk. Because the construction sat inside the per-question loop, the model was
built 28 times in a single evaluation run — visible as the repeated
`Loading weights: 105/105` lines in the server log.

Measured on this machine:

| Operation | Time |
| --- | --- |
| `CrossEncoder(...)` construction | **2,930 ms** |
| `predict()` over 20 chunks | **91 ms** |

Construction cost roughly 32× the inference it enabled, and accounted for about
half of the 5,758 ms average query latency.

**Fix.** Model loading is now cached at module level in
`app/retrieval/reranker.py`:

- `get_cross_encoder(model_name)` is wrapped in `functools.lru_cache`, so a given
  model is loaded at most once per process.
- `get_reranker()` returns a process-wide `Reranker`.
- `RAGEvaluator` accepts a `reranker` argument, and `/evaluate` passes the
  instance the API already built during `lifespan`. The evaluator and the request
  path now share one loaded model instead of holding two copies.
- `RAGEvaluator.relevance_model` uses the same cached loader, so the evaluator's
  scoring model and the reranker are the *same object* rather than two separate
  loads of identical weights.

**Why this shape.** Caching in the module rather than passing objects everywhere
keeps call sites unchanged while guaranteeing one load per process, including for
scripts and tests that never touch FastAPI's `lifespan`.

**Verified.** First `get_reranker()` call: 3,448 ms. Second call: 0.0 ms.

**Expected effect.** Average latency ~5,758 ms → ~2,830 ms, with no change to
output quality.

---

## 2. Faithfulness was measuring the wrong quantity

**Problem.** The metric compared the generated answer to the **expected answer**
by lexical token overlap. The standard definition used by RAGAS and TruLens is
different: faithfulness asks whether the answer's claims are supported by the
**retrieved context**. It never looks at a reference answer.

Because of that mismatch, correct answers were penalized for paraphrasing. The
clearest case from the run:

- Expected: *"About 32% of stored energy was lost over five days at 40°C."*
- Generated: *"…losses of 32 percent over 5 days at 40°C."*
- Score: **0.286**

Same fact, same numbers. It lost points because `percent` ≠ `%`, `5` ≠ `five`,
and the added citation inflated the token denominator.

A second symptom confirmed the diagnosis: as difficulty rose, context precision
*improved* (0.673 → 0.867) while faithfulness *fell* (0.890 → 0.474). If
faithfulness tracked grounding, the two would move together. They diverged
because harder questions have longer reference answers, so overlap drops
mechanically with the larger denominator.

**Fix.** `faithfulness` and `answer_correctness` are now two separate metrics.

**`faithfulness`** — answer vs. retrieved context:

1. **Numeric grounding check.** Every number in the answer must appear in the
   retrieved context. In technical documentation a fabricated number is the
   highest-signal hallucination, and this check is deterministic and free. If
   *no* number is grounded the score short-circuits to 0.0.
2. **LLM-as-judge.** The judge prompt explicitly instructs that restating the
   documents in different words is fully supported, so paraphrasing is not
   penalized.
3. **Fallback.** If the judge is disabled or errors, the numeric score is used;
   if the answer contains no numbers, content-word overlap **against the
   context** (not the reference) is used.

**`answer_correctness`** — answer vs. expected answer. This is the reference
comparison that used to be mislabeled as faithfulness. It is a legitimate metric,
just a different one, and it now uses an LLM judge with a normalized numeric-recall
fallback.

**Why keep both.** They fail for opposite reasons and imply opposite fixes:

- Low faithfulness, high correctness → generation is drifting from its context.
- High faithfulness, low correctness → generation is doing its job; **retrieval**
  never surfaced the needed chunk.

Collapsing them into one number hides which half of the pipeline is at fault.
`_classify_failure` now names the responsible stage instead of always reporting
`"Hallucination or incorrect retrieval"`.

**Supporting fix: text normalization.** Both metrics normalize before comparing,
so equal facts compare equal:

- Unit spellings: `watt-hours/kilogram` → `wh/kg`, `percent` → `%`,
  `newton-meters` → `n-m`, `miles per gallon` → `mpg`.
- Number words: `five` → `5`.
- Thousands separators: `6,000` → `6000`.
- **Citations are stripped before scoring.** `[Source: file.pdf, Chunk: 846]` is
  produced by the generator, not drawn from the document. Left in, the chunk
  number `846` was scored as an ungrounded numeric claim — the metric was
  penalizing answers for citing their sources.

**Verified.** On the pair that previously scored 0.286: numeric recall is now
`1.0`, correctness `1.0`, and the citation number `846` is correctly excluded
from the claim set.

---

## 3. Answer relevance returned 1.000 for every query

**Problem.** All 28 questions scored exactly 1.000. The cause:

```python
normalized = max(0.0, min(1.0, (score + 5) / 10))
```

MS-MARCO cross-encoders emit logits well above +5 for any plausible pair, so
every result clipped to the ceiling. A metric that returns an identical value for
all inputs carries no information, and the `relevance < 0.7` failure branch was
unreachable.

**Fix.** Replaced the linear rescale with a sigmoid. These models are trained
with a logistic loss, so the sigmoid is the calibrated way to turn a logit into a
probability. `context_precision` now thresholds on that probability via the
configurable `CONTEXT_RELEVANCE_THRESHOLD` rather than a bare `score > 0`.

**Verified.** Logits `[-6, -1, 0, 3, 8]` now map to `[0.002, 0.269, 0.5, 0.953,
1.0]` — real spread across the range instead of a constant.

**Outcome on the golden set: still 1.000 for all 28 questions.** The metric is now
correctly calibrated and does discriminate — an unrelated answer scores 0.000 —
but every answer the pipeline produces does address its question, so they all land
in the saturated tail of the sigmoid. The fix removed a bug; it did not make this
metric informative on this data. The useful signal is `context_precision`, which
uses the same model but thresholds per chunk. Treat answer relevance as a
regression guard that fires only when generation goes badly off-topic.

---

## 4. "Hybrid" search was running dense-only

**Problem.** `HybridSearch` built its BM25 index in process memory, and only
inside `upsert_chunks`. `sparse_search` opened with:

```python
if self.bm25 is None or not self.corpus:
    return []
```

Any process that had not itself ingested the document — every server restart, and
the entire evaluation run — silently fell back to pure dense retrieval. The
fusion step then blended dense scores against an empty set, so the documented
α=0.7 hybrid had never actually run against a populated sparse index.

This bore directly on the observed failures. BM25 is what recovers literal
tokens: `6,000 psi`, `65.3 mpg`, `17 seconds`. The one genuine retrieval miss and
both incomplete answers all turned on specific numeric spans — exactly what
sparse retrieval recovers and dense embeddings blur.

A second, quieter bug: `sparse_search` took no `namespace` argument, so BM25
results were never namespace-scoped even when the index was populated. In a
multi-tenant system that is a data-leak path between tenants.

**Fix.**

- The chunk corpus is persisted to `data/bm25/{namespace}.jsonl` at ingest time
  and lazily rebuilt into a BM25 index on first use, cached per namespace.
- `sparse_search` now takes `namespace` and only ever reads that namespace's
  corpus.
- Writes are keyed by `{source}_{chunk_index}`, matching the Pinecone vector id.
  Re-ingesting a document therefore overwrites its entries in both stores rather
  than accumulating duplicates in the sparse one.
- Writes go to a temp file and are then moved into place, so a crash mid-write
  cannot leave a partially written corpus.
- A shared tokenizer keeps `6,000` → `6000`, `n-m`, and `wh/kg` intact instead of
  letting naive `.split()` fragment them.

**Why files rather than a database.** Pinecone's sparse-vector support would be
the eventual production answer, but it requires re-indexing with sparse encodings.
A per-namespace corpus file fixes the correctness bug now, keeps the existing
index usable, and leaves that migration open.

**Verified.** Records survive across a brand-new `HybridSearch` instance; saving
the same chunks twice leaves 3 records rather than 6; a query for compressed
hydrogen returns the correct chunk; and a second namespace correctly sees nothing.

> **Action required:** `battery_line_1` was ingested before this change, so it has
> no corpus file yet and will stay dense-only until the document is re-ingested.
> Re-running `/ingest` is safe and idempotent.

---

## 5. Every `/query` embedded the question twice

**Problem.** Found while tracing the latency path in `app/main.py`:

```python
query_emb = search_engine.embedder.embed_query(question)   # embedding call 1
...
contexts = search_engine.hybrid_search(question, namespace, ...)  # embeds again
```

`query_emb` was computed only to time it, then discarded; `dense_search`
re-embedded the same string internally. Every request made two identical OpenAI
embedding calls — double the embedding latency and double the embedding cost, for
no benefit.

**Fix.** `dense_search` and `hybrid_search` accept an optional
`query_embedding`, and `/query` passes the vector it already computed. The
reported `embedding_latency_ms` now describes work that is actually used.

---

## 6. Golden-set questions were evaluated strictly serially

**Problem.** The evaluation loop ran 28 questions one at a time. Each question is
almost entirely I/O wait on OpenAI and Pinecone, so the process sat idle for most
of the run.

**Fix.** Questions are evaluated through a `ThreadPoolExecutor` sized by
`EVAL_CONCURRENCY` (default 4). `pool.map` preserves input order, so per-question
results still line up with the golden set.

Two safeguards:

- Cross-encoder inference is serialized behind a lock in `predict_pairs`, so
  worker threads share the single cached model safely.
- Concurrency defaults to a modest 4 rather than the full set, to stay clear of
  the OpenAI rate limits that this project has already hit.

Per-question `latency_ms` still measures that question alone; the new
`wall_clock_ms` field reports the true end-to-end duration of the run.

---

## 7. Configuration that was previously hard-coded

Values that were literals in the code are now settings in `app/config.py`, so
experiments no longer require editing source:

| Setting | Default | Purpose |
| --- | --- | --- |
| `RERANK_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Cross-encoder used for reranking and relevance |
| `HYBRID_ALPHA` | `0.7` | Dense/sparse fusion weight |
| `BM25_CORPUS_DIR` | `data/bm25` | Where the sparse corpus lives |
| `CONTEXT_RELEVANCE_THRESHOLD` | `0.5` | Probability above which a chunk counts as relevant |
| `EVAL_FAITHFULNESS_THRESHOLD` | `0.7` | Faithfulness score below which a query is reported as failing |
| `EVAL_CORRECTNESS_THRESHOLD` | `0.7` | Correctness score below which a query is reported as failing |
| `EVAL_CONCURRENCY` | `4` | Golden-set questions evaluated in parallel |

`hybrid_alpha` in the saved evaluation metadata previously carried the comment
`# This should be configurable` alongside a hard-coded `0.7`, which meant a saved
run recorded the wrong α if anyone passed a different value. It now reads from
settings, and the saved metadata also records the embedding, LLM, judge, and
rerank models so results remain comparable across configuration changes.

---

## Files changed

| File | Change |
| --- | --- |
| `app/retrieval/reranker.py` | Cached model loading, shared singleton, locked inference |
| `app/evaluation/metrics.py` | Split faithfulness/correctness, sigmoid relevance, normalization, parallel evaluation |
| `app/retrieval/hybrid_search.py` | Persistent namespace-scoped BM25, optional precomputed embedding |
| `app/main.py` | Shares the reranker, reuses the query embedding, reports correctness |
| `app/config.py` | New settings listed above |

## How to re-run

```bash
# 1. Re-ingest so the namespace gets a BM25 corpus (safe to repeat)
curl -X POST "http://localhost:8000/ingest" \
  -F "file=@data/sample_docs/advanced_automotive_technology.pdf" \
  -F "namespace=battery_line_1" \
  -F "strategy=recursive"

# 2. Re-run the evaluation
curl -X POST "http://localhost:8000/evaluate" \
  -F "namespace=battery_line_1"
```

## Measured results

Run on `battery_line_1`, 28 golden-set questions, 2,002 chunks
(`data/eval_results/eval_20260808_204946.json`).

| Metric | Before | After |
| --- | --- | --- |
| Faithfulness | 0.750 | 1.000 |
| Answer correctness | not measured | 0.912 |
| Answer relevance | 1.000 | 1.000 |
| Context precision | 0.757 | 0.771 |
| Avg latency | 5,758 ms | 2,945 ms |
| p95 latency | 7,443 ms | 5,106 ms |
| Wall clock (full set) | ~161 s (serial) | 35 s |
| Cost per query | $0.000153 | $0.000153 |

The old faithfulness number is not a like-for-like comparison: it measured
lexical overlap against the *expected answer*, so correct paraphrases were
scored as hallucinations. The two figures are listed together only to show what
changed, not as a quality delta.

Latency improved because the reranker is no longer reloaded per question and the
query embedding is computed once instead of twice. Wall-clock time improved
further from evaluating questions concurrently.

Per-difficulty correctness: easy 0.955, medium 0.932, hard 0.800. Faithfulness
is 1.000 in every bucket. The remaining 10 flagged queries split into 4
retrieval gaps (grounded answer, missing an expected fact) and 6 cases where the
answer was acceptable but fewer than half the retrieved chunks were relevant.
Both point at retrieval, not generation.

### Validating that the metrics are not degenerate

A faithfulness of exactly 1.000 on every question is the shape a broken metric
also produces, so the scorers were checked against deliberately wrong answers
using the same context:

| Answer | Faithfulness | Relevance |
| --- | --- | --- |
| Grounded restatement | 1.00 | 1.00 |
| Same claim, fabricated number | 0.00 | 1.00 |
| Unrelated claim | 0.00 | 0.00 |
| Half grounded, half invented | 0.50 | 1.00 |

Faithfulness separates fabrication from paraphrase, so 1.000 on the golden set
reflects a genuinely grounded generator rather than a metric that always agrees.

## Known limitations

- BM25 corpus files are per-process-local on disk. For multi-instance deployment
  this needs shared storage, or a move to Pinecone sparse vectors.
- The LLM judge adds one model call per borderline question. It is cheap on
  `gpt-4o-mini` but scales with golden-set size; `use_llm_judge=false` disables it
  and falls back to the deterministic path.
- The BM25 index is rebuilt in memory on first use per namespace. That is fine at
  the current corpus size, but a large corpus would want a prebuilt index.
- Answer relevance saturates at 1.000 on this golden set (see section 3). It only
  catches gross off-topic generation.
- The `gpt-4o-mini` judge is noisy on correctness. In spot checks it scored an
  answer equivalent to the reference at 0.5, so `avg_answer_correctness` is
  likely a slight underestimate. A stronger judge model, or averaging several
  samples, would tighten it.
