from typing import List
from openai import OpenAI
from app.config import get_settings


class OpenAIEmbedder:
    """OpenAI embeddings, truncated to the Pinecone index dimension."""

    def __init__(self):
        self.settings = get_settings()
        self.client = OpenAI(api_key=self.settings.OPENAI_API_KEY)
        self.model = self.settings.OPENAI_EMBEDDING_MODEL
        self.dimensions = self.settings.EMBEDDING_DIMENSIONS

    def embed(self, texts: List[str]) -> List[List[float]]:
        response = self.client.embeddings.create(
            model=self.model,
            input=texts,
            dimensions=self.dimensions,
        )
        return [item.embedding for item in response.data]

    def embed_query(self, text: str) -> List[float]:
        return self.embed([text])[0]
