import boto3
import json
import urllib.request
import urllib.error
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest


def enable_model(model_id, region="us-east-1"):
    """Enable a Bedrock model using the undocumented entitlement API."""
    
    session = boto3.Session(region_name=region)
    credentials = session.get_credentials()
    
    url = f"https://bedrock.{region}.amazonaws.com/foundation-model-entitlement"
    payload = json.dumps({"modelId": model_id})
    
    request = AWSRequest(
        method="POST",
        url=url,
        data=payload,
        headers={"Content-Type": "application/x-amz-json-1.1"}
    )
    
    SigV4Auth(credentials, "bedrock", region).add_auth(request)
    
    urllib_request = urllib.request.Request(
        url,
        data=request.body,
        headers=dict(request.headers),
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(urllib_request, timeout=30) as response:
            content = response.read().decode("utf-8")
            print(f"✓ {model_id}: Enabled successfully")
            return True
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        if "already entitled" in error_body.lower() or e.status == 409:
            print(f"✓ {model_id}: Already enabled")
            return True
        elif e.status == 403:
            print(f"✗ {model_id}: Access denied — account may be restricted")
            print(f"   Details: {error_body}")
        elif e.status == 404:
            print(f"✗ {model_id}: Model not found in {region}")
        else:
            print(f"✗ {model_id}: HTTP {e.status} — {error_body}")
        return False
    except Exception as e:
        print(f"✗ {model_id}: {str(e)}")
        return False


if __name__ == "__main__":
    models = [
        "amazon.titan-embed-text-v2:0",
        "anthropic.claude-3-sonnet-20240229-v1:0"
    ]
    
    print("Enabling Bedrock models...\n")
    results = {}
    for model in models:
        results[model] = enable_model(model)
    
    print("\n=== Summary ===")
    for model, success in results.items():
        status = "ENABLED" if success else "FAILED"
        print(f"{status:<10} | {model}")