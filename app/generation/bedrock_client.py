import json
from typing import List, Dict

import boto3
from botocore.config import Config

from app.config import get_settings


class BedrockGenerator:
    """Claude 3 Sonnet generation via AWS Bedrock."""

    def __init__(self):
        self.settings = get_settings()
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=self.settings.AWS_REGION,
            config=Config(retries={"max_attempts": 5, "mode": "adaptive"}),
        )
        self.model_id = self.settings.LLM_MODEL_ID

    def generate(self, question: str, contexts: List[dict]) -> Dict:
        context_block = "\n\n".join(
            f"[Source: {c.get('source', 'unknown')}, Chunk: {c.get('chunk_index', 0)}]\n{c['text']}"
            for c in contexts
        )
        system = (
            "You are a manufacturing documentation assistant. "
            "Answer only from the provided context. "
            "Cite sources as [Source: filename, Chunk: N]. "
            "If the context is insufficient, say you don't have sufficient information."
        )
        user_message = (
            f"Context:\n{context_block}\n\n"
            f"Question: {question}\n\n"
            "Answer:"
        )

        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1024,
            "temperature": 0.1,
            "system": system,
            "messages": [{"role": "user", "content": user_message}],
        }

        response = self.client.invoke_model(
            modelId=self.model_id,
            body=json.dumps(body),
            accept="application/json",
            contentType="application/json",
        )
        result = json.loads(response["body"].read())
        answer = "".join(
            block.get("text", "")
            for block in result.get("content", [])
            if block.get("type") == "text"
        )
        usage = result.get("usage", {})
        return {
            "answer": answer.strip(),
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
        }
