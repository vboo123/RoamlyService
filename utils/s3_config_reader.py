import boto3
import os
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup S3 client
s3_client = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION", "us-east-2")
)
S3_BUCKET = os.getenv("S3_BUCKET_NAME")

def read_json_from_s3(s3_key: str) -> dict:
    """Read JSON file from S3"""
    try:
        response = s3_client.get_object(Bucket=S3_BUCKET, Key=s3_key)
        content = response['Body'].read().decode('utf-8')
        return json.loads(content)
    except Exception as e:
        print(f"❌ Failed to read {s3_key} from S3: {e}")
        raise

def get_landmarks_from_s3() -> list:
    """Get landmarks.json from S3"""
    return read_json_from_s3("config/landmarks.json")

def get_semantic_config_from_s3() -> dict:
    """Get semantic_config.json from S3"""
    return read_json_from_s3("config/semantic_config.json") 