import time
import random
import json
import os
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.ingestion.loader import DocumentLoader
from app.ingestion.chunker import Chunker
from app.retrieval.hybrid_search import HybridSearch
from app.retrieval.reranker import Reranker
from app.generation.openai_client import OpenAIGenerator
from app.generation.guardrails import Guardrails
from app.monitoring.cost_tracker import CostTracker, QueryMetrics


# Global state
search_engine = None
reranker = None
generator = None
cost_tracker = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global search_engine, reranker, generator, cost_tracker
    search_engine = HybridSearch()
    reranker = Reranker()
    generator = OpenAIGenerator()
    cost_tracker = CostTracker()
    yield


app = FastAPI(
    title="Manufacturing RAG Platform",
    description="Production RAG for manufacturing documentation",
    version="1.0.0",
    lifespan=lifespan
)


@app.post("/ingest")
async def ingest_document(
    file: UploadFile = File(...),
    namespace: str = Form("default"),
    strategy: str = Form("recursive")
):
    """Ingest a manufacturing document into the RAG system."""
    start_time = time.time()
    
    # Load
    content = await file.read()
    text = DocumentLoader.load_file(content, file.filename)
    
    # Chunk
    chunker = Chunker(
        chunk_size=get_settings().CHUNK_SIZE,
        chunk_overlap=get_settings().CHUNK_OVERLAP
    )
    chunks = chunker.chunk(text, source=file.filename, strategy=strategy)
    
    # Embed and store
    search_engine.upsert_chunks(chunks, namespace=namespace)
    
    latency = (time.time() - start_time) * 1000
    
    return {
        "status": "success",
        "filename": file.filename,
        "chunks_created": len(chunks),
        "namespace": namespace,
        "strategy": strategy,
        "ingestion_time_ms": round(latency, 2)
    }


@app.post("/query")
async def query(
    question: str = Form(...),
    namespace: str = Form("default"),
    strategy: str = Form("recursive"),
    use_hybrid: bool = Form(True),
    use_rerank: bool = True
):
    """Query the manufacturing knowledge base."""
    total_start = time.time()
    settings = get_settings()
    
    # Guardrails
    is_safe, reason = Guardrails.check_input(question)
    if not is_safe:
        raise HTTPException(status_code=400, detail=f"Guardrail: {reason}")
    
    metrics = QueryMetrics(strategy=strategy)
    
    # 1. Embed query
    embed_start = time.time()
    query_emb = search_engine.embedder.embed_query(question)
    embed_end = time.time()
    metrics.embedding_latency_ms = (embed_end - embed_start) * 1000
    
    # 2. Retrieve
    retrieve_start = time.time()
    if use_hybrid:
        contexts = search_engine.hybrid_search(question, namespace, top_k=settings.TOP_K_DENSE)
    else:
        contexts = search_engine.dense_search(question, namespace, top_k=settings.TOP_K_DENSE)
    retrieve_end = time.time()
    metrics.retrieval_latency_ms = (retrieve_end - retrieve_start) * 1000
    
    # 3. Rerank
    if use_rerank and contexts:
        contexts = reranker.rerank(question, contexts, top_k=settings.TOP_K_RERANK)
    
    # Guardrail: no context
    if not contexts:
        return {
            "answer": "I don't have sufficient information in the documentation to answer this.",
            "sources": [],
            "metrics": {"total_latency_ms": round((time.time() - total_start) * 1000, 2)}
        }
    
    # 4. Generate
    gen_start = time.time()
    gen_result = generator.generate(question, contexts)
    gen_end = time.time()
    metrics.generation_latency_ms = (gen_end - gen_start) * 1000
    metrics.input_tokens = gen_result["input_tokens"]
    metrics.output_tokens = gen_result["output_tokens"]
    
    # Cost calculation
    embed_tokens = sum(len(c["text"].split()) for c in contexts) + len(question.split())
    metrics.embedding_cost = CostTracker.estimate_embedding_cost(int(embed_tokens * 0.75))
    metrics.generation_cost = CostTracker.estimate_generation_cost(
        gen_result["input_tokens"], 
        gen_result["output_tokens"]
    )
    
    # Total latency
    total_end = time.time()
    metrics.total_latency_ms = (total_end - total_start) * 1000
    
    # Global cost guardrail
    if metrics.total_cost > settings.MAX_COST_PER_QUERY:
        raise HTTPException(
            status_code=429, 
            detail=f"Query cost ${metrics.total_cost:.4f} exceeds limit ${settings.MAX_COST_PER_QUERY}"
        )
    
    cost_tracker.record(metrics)
    
    # Output guardrail
    is_safe, reason = Guardrails.check_output(gen_result["answer"])
    if not is_safe:
        gen_result["answer"] = f"[Output filtered: {reason}]"
    
    return {
        "answer": gen_result["answer"],
        "sources": [
            {"source": c["source"], "chunk_index": c.get("chunk_index", 0)}
            for c in contexts
        ],
        "retrieval_strategy": "hybrid" if use_hybrid else "dense",
        "chunking_strategy": strategy,
        "metrics": {
            "total_latency_ms": round(metrics.total_latency_ms, 2),
            "retrieval_latency_ms": round(metrics.retrieval_latency_ms, 2),
            "generation_latency_ms": round(metrics.generation_latency_ms, 2),
            "input_tokens": metrics.input_tokens,
            "output_tokens": metrics.output_tokens,
            "total_cost_usd": round(metrics.total_cost, 6)
        }
    }

# Add this endpoint to your app/main.py, inside the FastAPI app

@app.post("/evaluate")
async def evaluate(
    namespace: str = Form("default"),
    golden_set: str = Form("data/golden_set/golden_set.jsonl")
):
    """
    Run golden set evaluation against a namespace.

    Returns aggregated metrics (faithfulness, relevance, precision, latency, cost)
    plus per-difficulty breakdowns and failed query analysis.
    """
    from app.evaluation.metrics import RAGEvaluator

    if not os.path.exists(golden_set):
        raise HTTPException(status_code=404, detail=f"Golden set not found: {golden_set}")

    evaluator = RAGEvaluator(search_engine, generator)
    results = evaluator.evaluate(golden_set, namespace, use_llm_judge=True)
    saved_path = evaluator.save_eval_result(results)

    return {
        "status": "success",
        "namespace": namespace,
        "golden_set": golden_set,
        "summary": {
            "total_evaluated": results["total_evaluated"],
            "avg_faithfulness": results["avg_faithfulness"],
            "avg_answer_relevance": results["avg_answer_relevance"],
            "avg_context_precision": results["avg_context_precision"],
            "avg_latency_ms": results["avg_latency_ms"],
            "p95_latency_ms": results["p95_latency_ms"],
            "avg_cost_per_query": results["avg_cost_per_query"]
        },
        "by_difficulty": results["by_difficulty"],
        "failed_queries": results["failed_queries"],
        "total_failures": len(results["failed_queries"])
    }

@app.get("/metrics")
async def get_metrics():
    """Get aggregated platform metrics."""
    return cost_tracker.get_stats()


@app.get("/health")
async def health():
    return {"status": "healthy", "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)