import boto3
import os
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

def upload_file_to_s3(local_file_path: str, s3_key: str, content_type: str = "application/json"):
    """Upload a file to S3"""
    try:
        with open(local_file_path, 'rb') as file:
            s3_client.upload_fileobj(
                file,
                S3_BUCKET,
                s3_key,
                ExtraArgs={'ContentType': content_type}
            )
        print(f"✅ Uploaded {local_file_path} to s3://{S3_BUCKET}/{s3_key}")
    except Exception as e:
        print(f"❌ Failed to upload {local_file_path}: {e}")

def main():
    """Upload configuration files to S3"""
    print("🚀 Uploading configuration files to S3...")
    
    # Upload landmarks.json
    upload_file_to_s3("scripts/landmarks.json", "config/landmarks.json")
    
    # Upload semantic_config.json
    upload_file_to_s3("scripts/semantic_config.json", "config/semantic_config.json")
    
    # Upload new registration option files
    upload_file_to_s3("scripts/countries.json", "config/countries.json")
    upload_file_to_s3("scripts/languages.json", "config/languages.json")
    upload_file_to_s3("scripts/interests.json", "config/interests.json")
    
    print("✅ Configuration upload complete!")

if __name__ == "__main__":
    main() 