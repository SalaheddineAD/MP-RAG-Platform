import boto3
import json

bedrock = boto3.client("bedrock", region_name="us-east-1")

print("=== Foundation Models Available to Your Account ===\n")
try:
    response = bedrock.list_foundation_models()
    for model in response.get("modelSummaries", []):
        model_id = model.get("modelId", "N/A")
        provider = model.get("providerName", "N/A")
        lifecycle = model.get("modelLifecycle", {}).get("status", "UNKNOWN")
        # Check if inference is supported
        inference_types = model.get("inferenceTypesSupported", [])
        print(f"{provider:<15} | {model_id:<50} | {lifecycle:<10} | {inference_types}")
except Exception as e:
    print(f"Error: {e}")