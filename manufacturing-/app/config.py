from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # AWS
    AWS_REGION: str = "us-east-1"
    
    # Pinecone
    PINECONE_API_KEY: str
    PINECONE_INDEX_NAME: str = "manufacturing-rag"
    PINECONE_NAMESPACE: str = "default"
    
    # Bedrock
    EMBEDDING_MODEL_ID: str = "amazon.titan-embed-text-v2:0"
    LLM_MODEL_ID: str = "anthropic.claude-3-sonnet-20240229-v1:0"
    
    # Retrieval
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 50
    TOP_K_DENSE: int = 20
    TOP_K_RERANK: int = 5
    
    # A/B Test
    CHUNK_STRATEGY: str = "recursive"  # recursive | semantic | agentic
    
    # Cost Guardrails
    MAX_COST_PER_QUERY: float = 0.01  # dollars
    
    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()