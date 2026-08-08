import boto3, json, time

client = boto3.client("bedrock-runtime", region_name="us-east-1")

# Test with the smallest possible request
try:
    response = client.invoke_model(
        modelId="amazon.titan-embed-text-v2:0",
        body=json.dumps({"inputText": "hello"}),
        accept="application/json",
        contentType="application/json"
    )
    result = json.loads(response["body"].read())
    print(f"✓ Bedrock works! Embedding dim: {len(result['embedding'])}")
except Exception as e:
    print(f"✗ Error: {e}")
    print(f"Error type: {type(e).__name__}")