#*****************************************************
# Run from project root:
#   python -m app.tests.test_setup
# or:
#   python app/tests/test_setup.py
#*****************************************************
import sys
from pathlib import Path

# Ensure project root is on sys.path when run as a script
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import boto3
import json
from pinecone import Pinecone
from app.config import get_settings

settings = get_settings()

# Test Bedrock
try:
    bedrock = boto3.client("bedrock-runtime", region_name=settings.AWS_REGION)
    response = bedrock.invoke_model(
        modelId="amazon.titan-embed-text-v2:0",
        body=json.dumps({"inputText": "test"}),
        accept="application/json",
        contentType="application/json",
    )
    result = json.loads(response["body"].read())
    print(f"✓ Bedrock works! Embedding dim: {len(result['embedding'])}")
except Exception as e:
    print(f"✗ Bedrock failed: {e}")

# Test Pinecone
try:
    pc = Pinecone(api_key=settings.PINECONE_API_KEY)
    index = pc.Index(settings.PINECONE_INDEX_NAME)
    stats = index.describe_index_stats()
    print(f"✓ Pinecone connected! Vectors: {stats.total_vector_count}")
except Exception as e:
    print(f"✗ Pinecone failed: {e}")
