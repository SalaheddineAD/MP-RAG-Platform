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

from openai import OpenAI
from pinecone import Pinecone
from app.config import get_settings

settings = get_settings()
client = OpenAI(api_key=settings.OPENAI_API_KEY)

# Test OpenAI embeddings
try:
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input="test",
    )
    print(f"✓ OpenAI embeddings work! Dim: {len(response.data[0].embedding)}")
except Exception as e:
    print(f"✗ OpenAI embeddings failed: {e}")

# Test OpenAI chat
try:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Say ok"}],
        max_tokens=5,
    )
    print(f"✓ OpenAI chat works! Reply: {response.choices[0].message.content}")
except Exception as e:
    print(f"✗ OpenAI chat failed: {e}")

# Test Pinecone
try:
    pc = Pinecone(api_key=settings.PINECONE_API_KEY)
    index = pc.Index(settings.PINECONE_INDEX_NAME)
    stats = index.describe_index_stats()
    print(f"✓ Pinecone connected! Vectors: {stats.total_vector_count}")
except Exception as e:
    print(f"✗ Pinecone failed: {e}")
