from typing import List
from openai import OpenAI
from app.config import get_settings


class OpenAIEmbedder:
    """OpenAI text-embedding-3-small: 1536 dims, cheap, no throttling."""
    
    def __init__(self):
        self.settings = get_settings()
        self.client = OpenAI(api_key=self.settings.OPENAI_API_KEY)
        self.model = self.settings.OPENAI_EMBEDDING_MODEL
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        response = self.client.embeddings.create(
            model=self.model,
            input=texts
        )
        return [item.embedding for item in response.data]
    
    def embed_query(self, text: str) -> List[float]:
        return self.embed([text])[0]