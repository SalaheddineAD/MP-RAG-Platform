from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    OPENAI_API_KEY: str
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    OPENAI_LLM_MODEL: str = "gpt-4o-mini"
    OPENAI_JUDGE_MODEL: str = "gpt-4o-mini"
    # Must match the dimension of the Pinecone index
    EMBEDDING_DIMENSIONS: int = 1024

    PINECONE_API_KEY: str
    PINECONE_INDEX_NAME: str = "manufacturing-rag"
    PINECONE_NAMESPACE: str = "default"

    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 50
    TOP_K_DENSE: int = 20
    TOP_K_RERANK: int = 5

    RERANK_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    # Dense/sparse fusion weight: 1.0 is dense-only, 0.0 is BM25-only
    HYBRID_ALPHA: float = 0.7
    # BM25 needs the chunk text on disk to survive process restarts
    BM25_CORPUS_DIR: str = "data/bm25"

    # A chunk counts toward context precision above this relevance probability
    CONTEXT_RELEVANCE_THRESHOLD: float = 0.5
    # A golden-set question is reported as failing below these scores
    EVAL_FAITHFULNESS_THRESHOLD: float = 0.7
    EVAL_CORRECTNESS_THRESHOLD: float = 0.7
    # Golden-set questions evaluated in parallel; each is I/O-bound on OpenAI/Pinecone
    EVAL_CONCURRENCY: int = 4

    CHUNK_STRATEGY: str = "recursive"
    MAX_COST_PER_QUERY: float = 0.01

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()