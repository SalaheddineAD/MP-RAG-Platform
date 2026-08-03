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
import time
import json
from pinecone import Pinecone
from app.config import get_settings

settings = get_settings()


# Try v1
try:
    response = client.invoke_model(
        modelId="amazon.titan-embed-text-v1",
        body=json.dumps({"inputText": "hello world"}),
        accept="application/json",
        contentType="application/json"
    )
    result = json.loads(response["body"].read())
    print(f"✓ Titan v1 works! Dim: {len(result['embedding'])}")
except Exception as e:
    print(f"✗ Titan v1 failed: {e}")

time.sleep(2)

# Try v2 again
try:
    response = client.invoke_model(
        modelId="amazon.titan-embed-text-v2:0",
        body=json.dumps({"inputText": "hello world"}),
        accept="application/json",
        contentType="application/json"
    )
    result = json.loads(response["body"].read())
    print(f"✓ Titan v2 works! Dim: {len(result['embedding'])}")
except Exception as e:
    print(f"✗ Titan v2 failed: {e}")
