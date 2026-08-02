import json
import boto3
from typing import List
from app.config import get_settings


class BedrockEmbedder:
    """AWS Bedrock Titan embeddings."""
    
    def __init__(self):
        self.settings = get_settings()
        self.client = boto3.client("bedrock-runtime", region_name=self.settings.AWS_REGION)
        self.model_id = self.settings.EMBEDDING_MODEL_ID
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        """Batch embedding with Bedrock."""
        embeddings = []
        
        # Bedrock embeds one at a time for Titan v2
        for text in texts:
            body = json.dumps({"inputText": text})
            
            response = self.client.invoke_model(
                modelId=self.model_id,
                body=body,
                accept="application/json",
                contentType="application/json"
            )
            
            result = json.loads(response["body"].read())
            embeddings.append(result["embedding"])
        
        return embeddings
    
    def embed_query(self, text: str) -> List[float]:
        return self.embed([text])[0]