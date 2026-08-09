import json
import re
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional, Tuple

import numpy as np
from pinecone import Pinecone
from rank_bm25 import BM25Okapi

from app.config import get_settings
from app.ingestion.embedder import OpenAIEmbedder

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[./-][a-z0-9]+)*")


def tokenize(text: str) -> List[str]:
    """Lowercase tokenizer that keeps 45n-m, 6,000 and w/kg style tokens intact."""
    return _TOKEN_RE.findall(text.lower().replace(",", ""))


class HybridSearch:
    """Dense (Pinecone) + sparse (BM25) retrieval with score fusion."""

    def __init__(self):
        self.settings = get_settings()
        self.pc = Pinecone(api_key=self.settings.PINECONE_API_KEY)
        self.index = self.pc.Index(self.settings.PINECONE_INDEX_NAME)
        self.embedder = OpenAIEmbedder()
        self._verify_index_dimension()

        self.corpus_dir = Path(self.settings.BM25_CORPUS_DIR)
        self._bm25_cache: Dict[str, Tuple[BM25Okapi, List[dict]]] = {}
        self._cache_lock = Lock()

    def _verify_index_dimension(self):
        """Fail at startup rather than mid-ingest if embeddings won't fit the index."""
        index_dim = self.index.describe_index_stats().dimension
        if index_dim != self.embedder.dimensions:
            raise ValueError(
                f"Pinecone index '{self.settings.PINECONE_INDEX_NAME}' has dimension "
                f"{index_dim}, but embeddings are {self.embedder.dimensions}. "
                f"Set EMBEDDING_DIMENSIONS={index_dim} or recreate the index."
            )

    # ---------- BM25 corpus persistence ----------

    def _corpus_path(self, namespace: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", namespace) or "default"
        return self.corpus_dir / f"{safe}.jsonl"

    def _save_to_corpus(self, chunks: List[dict], namespace: str):
        """Merge chunks into the namespace corpus, keyed like the Pinecone vector ids.

        Re-ingesting a document overwrites its vectors in Pinecone, so the sparse
        corpus has to behave the same way instead of accumulating duplicates.
        """
        path = self._corpus_path(namespace)
        path.parent.mkdir(parents=True, exist_ok=True)

        records: Dict[str, dict] = {}
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        rec = json.loads(line)
                        records[f"{rec['source']}_{rec.get('chunk_index', 0)}"] = rec

        for chunk in chunks:
            rec = {
                "text": chunk["text"],
                "source": chunk["source"],
                "chunk_index": chunk.get("chunk_index", 0),
            }
            records[f"{rec['source']}_{rec['chunk_index']}"] = rec

        tmp = path.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for rec in records.values():
                f.write(json.dumps(rec) + "\n")
        tmp.replace(path)

        with self._cache_lock:
            self._bm25_cache.pop(namespace, None)

    def _load_bm25(self, namespace: str) -> Optional[Tuple[BM25Okapi, List[dict]]]:
        """Build the BM25 index for a namespace from disk, cached per process."""
        with self._cache_lock:
            cached = self._bm25_cache.get(namespace)
        if cached is not None:
            return cached

        path = self._corpus_path(namespace)
        if not path.exists():
            return None

        records: List[dict] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        if not records:
            return None

        bm25 = BM25Okapi([tokenize(r["text"]) for r in records])
        built = (bm25, records)
        with self._cache_lock:
            self._bm25_cache[namespace] = built
        return built

    # ---------- Indexing ----------

    def upsert_chunks(self, chunks: List[dict], namespace: str):
        texts = [c["text"] for c in chunks]
        embeddings = self.embedder.embed(texts)

        vectors = []
        for chunk, emb in zip(chunks, embeddings):
            vectors.append({
                "id": f"{chunk['source']}_{chunk['chunk_index']}",
                "values": emb,
                "metadata": {
                    "text": chunk["text"],
                    "source": chunk["source"],
                    "strategy": chunk.get("strategy", "recursive"),
                    "chunk_index": chunk["chunk_index"]
                }
            })

        batch_size = 100
        for i in range(0, len(vectors), batch_size):
            self.index.upsert(vectors=vectors[i:i+batch_size], namespace=namespace)

        self._save_to_corpus(chunks, namespace)

    # ---------- Retrieval ----------

    def dense_search(
        self,
        query: str,
        namespace: str,
        top_k: int = 20,
        query_embedding: Optional[List[float]] = None,
    ) -> List[dict]:
        # Callers that already embedded the query pass it in to avoid a second API call.
        query_emb = query_embedding if query_embedding is not None else self.embedder.embed_query(query)
        results = self.index.query(
            vector=query_emb,
            top_k=top_k,
            namespace=namespace,
            include_metadata=True
        )
        return [
            {
                "text": match.metadata["text"],
                "source": match.metadata["source"],
                "score": match.score,
                "chunk_index": match.metadata.get("chunk_index", 0)
            }
            for match in results.matches
        ]

    def sparse_search(self, query: str, namespace: str, top_k: int = 20) -> List[dict]:
        loaded = self._load_bm25(namespace)
        if loaded is None:
            return []
        bm25, records = loaded

        scores = bm25.get_scores(tokenize(query))
        top_indices = np.argsort(scores)[-top_k:][::-1]
        return [
            {
                "text": records[i]["text"],
                "source": records[i]["source"],
                "score": float(scores[i]),
                "chunk_index": records[i].get("chunk_index", 0)
            }
            for i in top_indices if scores[i] > 0
        ]

    def hybrid_search(
        self,
        query: str,
        namespace: str,
        top_k: int = 20,
        alpha: Optional[float] = None,
        query_embedding: Optional[List[float]] = None,
    ) -> List[dict]:
        if alpha is None:
            alpha = self.settings.HYBRID_ALPHA

        dense_results = self.dense_search(
            query, namespace, top_k=top_k, query_embedding=query_embedding
        )
        sparse_results = self.sparse_search(query, namespace, top_k=top_k)

        def normalize_scores(results):
            if not results:
                return {}
            scores = [r["score"] for r in results]
            max_s, min_s = max(scores), min(scores)
            if max_s == min_s:
                return {f"{r['source']}_{r['chunk_index']}": 1.0 for r in results}
            return {f"{r['source']}_{r['chunk_index']}": (r["score"] - min_s) / (max_s - min_s) for r in results}

        dense_norm = normalize_scores(dense_results)
        sparse_norm = normalize_scores(sparse_results)
        all_keys = set(dense_norm.keys()) | set(sparse_norm.keys())
        fused = {key: alpha * dense_norm.get(key, 0.0) + (1 - alpha) * sparse_norm.get(key, 0.0) for key in all_keys}
        sorted_keys = sorted(fused.keys(), key=lambda k: fused[k], reverse=True)[:top_k]
        text_map = {f"{r['source']}_{r['chunk_index']}": r for r in dense_results + sparse_results}
        return [text_map[k] for k in sorted_keys if k in text_map]
