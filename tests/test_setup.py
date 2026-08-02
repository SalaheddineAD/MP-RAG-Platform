import boto3
from pinecone import Pinecone
from app.config import get_settings

# Test AWS Bedrock
settings = get_settings()
bedrock = boto3.client("bedrock-runtime", region_name=settings.AWS_REGION)
print("✓ AWS Bedrock client created")

# Test Pinecone
pc = Pinecone(api_key=settings.PINECONE_API_KEY)
print(f"✓ Pinecone connected: {pc.list_indexes()}")