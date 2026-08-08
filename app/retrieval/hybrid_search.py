from typing import List, Dict
import numpy as np
from pinecone import Pinecone
from rank_bm25 import BM25Okapi
from app.config import get_settings
from app.ingestion.embedder import OpenAIEmbedder


class HybridSearch:
    """Dense + sparse retrieval with Pinecone."""
    
    def __init__(self):
        self.settings = get_settings()
        self.pc = Pinecone(api_key=self.settings.PINECONE_API_KEY)
        self.index = self.pc.Index(self.settings.PINECONE_INDEX_NAME)
        self.embedder = OpenAIEmbedder()
        
        self.bm25 = None
        self.corpus = []
        self.chunk_metadata = []
    
    def upsert_chunks(self, chunks: List[dict], namespace: str):
        texts = [c["text"] for c in chunks]
        embeddings = self.embedder.embed(texts)
        
        vectors = []
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
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
        
        self.corpus.extend(texts)
        self.chunk_metadata.extend(chunks)
        tokenized = [doc.split() for doc in self.corpus]
        self.bm25 = BM25Okapi(tokenized)
    
    def dense_search(self, query: str, namespace: str, top_k: int = 20) -> List[dict]:
        query_emb = self.embedder.embed_query(query)
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
    
    def sparse_search(self, query: str, top_k: int = 20) -> List[dict]:
        if self.bm25 is None or not self.corpus:
            return []
        tokenized_query = query.split()
        scores = self.bm25.get_scores(tokenized_query)
        top_indices = np.argsort(scores)[-top_k:][::-1]
        return [
            {
                "text": self.corpus[i],
                "source": self.chunk_metadata[i]["source"],
                "score": float(scores[i]),
                "chunk_index": self.chunk_metadata[i].get("chunk_index", 0)
            }
            for i in top_indices if scores[i] > 0
        ]
    
    def hybrid_search(self, query: str, namespace: str, top_k: int = 20, alpha: float = 0.7) -> List[dict]:
        dense_results = self.dense_search(query, namespace, top_k=top_k)
        sparse_results = self.sparse_search(query, top_k=top_k)
        
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