import json
import time
import random
import boto3
from typing import List
from botocore.config import Config
from botocore.exceptions import ClientError
from app.config import get_settings


class BedrockEmbedder:
    """AWS Bedrock Titan embeddings with retry logic."""
    
    def __init__(self):
        self.settings = get_settings()
        self.client = boto3.client(
            "bedrock-runtime", 
            region_name=self.settings.AWS_REGION,
            config=Config(
                retries={"max_attempts": 10, "mode": "adaptive"}
            )
        )
        self.model_id = self.settings.EMBEDDING_MODEL_ID
    
    def _invoke_with_backoff(self, body: str):
        """Exponential backoff with jitter for Bedrock throttling."""
        max_retries = 5
        base_delay = 1.0  # seconds
        
        for attempt in range(max_retries):
            try:
                return self.client.invoke_model(
                    modelId=self.model_id,
                    body=body,
                    accept="application/json",
                    contentType="application/json"
                )
            except ClientError as e:
                error_code = e.response['Error']['Code']
                if error_code == 'ThrottlingException' and attempt < max_retries - 1:
                    # Exponential backoff + jitter: 1s, 2s, 4s, 8s, 16s
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                    print(f"  Throttled. Retrying in {delay:.1f}s... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(delay)
                else:
                    raise
        
        raise Exception("Max retries exceeded for Bedrock embedding")
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        """Batch embedding with Bedrock and adaptive retry."""
        embeddings = []
        
        for text in texts:
            body = json.dumps({"inputText": text})
            response = self._invoke_with_backoff(body)
            result = json.loads(response["body"].read())
            embeddings.append(result["embedding"])
        
        return embeddings
    
    def embed_query(self, text: str) -> List[float]:
        return self.embed([text])[0]