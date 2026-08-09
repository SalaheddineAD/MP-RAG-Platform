#*****************************************************
# Run from project root:
#   python -m app.tests.test_openai
# or:
#   python app/tests/test_openai.py
#*****************************************************
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.ingestion.embedder import OpenAIEmbedder
from app.generation.openai_client import OpenAIGenerator

settings = get_settings()

# Embeddings: verify the model responds and the dimension matches the Pinecone index
try:
    embedder = OpenAIEmbedder()
    vector = embedder.embed_query("torque specification for battery mount")
    print(f"✓ Embeddings work ({embedder.model})! Dim: {len(vector)}")
    if len(vector) != settings.EMBEDDING_DIMENSIONS:
        print(f"  ! Expected {settings.EMBEDDING_DIMENSIONS} dims, got {len(vector)}")
except Exception as e:
    print(f"✗ Embeddings failed: {type(e).__name__}: {e}")

# Generation: verify the model answers from context and reports token usage
try:
    generator = OpenAIGenerator()
    contexts = [
        {
            "text": "The battery mount bolts are torqued to 45 N-m (33 lb-ft).",
            "source": "battery_spec.pdf",
            "chunk_index": 12,
        }
    ]
    result = generator.generate("What is the torque spec for the battery mount?", contexts)
    print(f"✓ Generation works ({generator.model})!")
    print(f"  Answer: {result['answer']}")
    print(f"  Tokens: in={result['input_tokens']} out={result['output_tokens']}")
    if "45" not in result["answer"]:
        print("  ! Answer did not cite the value from the provided context")
except Exception as e:
    print(f"✗ Generation failed: {type(e).__name__}: {e}")
    