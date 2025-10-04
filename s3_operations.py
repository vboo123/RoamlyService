import boto3
import json
import os
from datetime import datetime
from botocore.exceptions import ClientError

# === Setup S3 ===
def get_s3_client():
    """Get S3 client with current environment variables"""
    return boto3.client(
        "s3",
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=os.getenv("AWS_REGION", "us-east-2")
    )

def create_customer_bucket(customer_id: str, username: str) -> dict:
    """
    Creates an empty S3 bucket for a customer if it doesn't exist.
    
    Args:
        customer_id: The customer's unique identifier
        username: The customer's username
        
    Returns:
        dict: Status message indicating success or failure
    """
    # S3 bucket names must be lowercase and can only contain letters, numbers, and hyphens
    bucket_name = f"{customer_id}-{username}-bucket".lower()
    
    s3_client = get_s3_client()
    
    try:
        # Check if bucket already exists
        s3_client.head_bucket(Bucket=bucket_name)
        print(f"✅ Bucket {bucket_name} already exists")
        return {
            "status": "success",
            "message": f"{bucket_name} already exists",
            "bucket_name": bucket_name
        }
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        
        if error_code == '404':
            # Bucket doesn't exist, create it
            try:
                # Get the region from the S3 client
                region = s3_client.meta.region_name
                
                if region == 'us-east-1':
                    # us-east-1 doesn't need LocationConstraint
                    s3_client.create_bucket(Bucket=bucket_name)
                else:
                    # Other regions need LocationConstraint
                    s3_client.create_bucket(
                        Bucket=bucket_name,
                        CreateBucketConfiguration={'LocationConstraint': region}
                    )
                
                print(f"✅ Successfully created bucket: {bucket_name}")
                
                # Create the folder structure
                _create_bucket_structure(bucket_name)
                
                return {
                    "status": "success",
                    "message": f"Successfully created bucket: {bucket_name}",
                    "bucket_name": bucket_name
                }
                
            except ClientError as create_error:
                print(f"❌ Failed to create bucket {bucket_name}: {create_error}")
                return {
                    "status": "error",
                    "message": f"Failed to create bucket: {create_error}",
                    "bucket_name": bucket_name
                }
        else:
            # Other error (permissions, etc.)
            print(f"❌ Error checking bucket {bucket_name}: {e}")
            return {
                "status": "error",
                "message": f"Error checking bucket: {e}",
                "bucket_name": bucket_name
            }

def _create_bucket_structure(bucket_name: str):
    """
    Creates the initial folder structure in the S3 bucket.
    
    Args:
        bucket_name: Name of the S3 bucket
    """
    s3_client = get_s3_client()
    
    try:
        # Create empty folders by uploading empty objects with trailing slashes
        folder_structure = [
            "trips/",
            "tours/"
        ]
        
        for folder in folder_structure:
            s3_client.put_object(
                Bucket=bucket_name,
                Key=folder,
                Body=b''
            )
            print(f"✅ Created folder: {folder}")
            
    except ClientError as e:
        print(f"❌ Error creating bucket structure: {e}")

def deep_update(original: dict, updates: dict) -> dict:
    """
    Recursively merges updates into the original dict.
    - Nested dicts are updated in-place (not replaced).
    - Lists are appended to and deduplicated.
    - Scalar values are replaced.
    - Supports deletion with "__delete__" key for lists.
    
    Args:
        original: The original dictionary to update
        updates: The updates to merge in
        
    Returns:
        dict: The updated dictionary
    """
    for key, value in updates.items():
        if key == "__delete__":
            # Handle deletion requests
            if isinstance(value, list) and isinstance(original, dict):
                # Remove items from the original dict's lists
                for delete_key in value:
                    if delete_key in original and isinstance(original[delete_key], list):
                        original[delete_key] = [x for x in original[delete_key] if x not in value]
            continue
            
        if isinstance(value, dict) and isinstance(original.get(key), dict):
            # Merge nested dictionaries
            deep_update(original[key], value)
        elif isinstance(value, list) and isinstance(original.get(key), list):
            # Handle deletion within lists
            if "__delete__" in value:
                # Remove items marked for deletion
                items_to_remove = value["__delete__"]
                original[key] = [x for x in original[key] if x not in items_to_remove]
                # Remove the __delete__ key from the list
                value = [x for x in value if x != "__delete__"]
            
            # Merge and deduplicate list items
            merged_list = original[key] + value
            # Preserve order while removing duplicates
            seen = set()
            original[key] = [x for x in merged_list if not (x in seen or seen.add(x))]
        else:
            # Overwrite or add new keys
            original[key] = value
    return original

def get_persona_from_s3(bucket_name: str, key: str) -> dict:
    """
    Retrieves a persona JSON file from S3.
    
    Args:
        bucket_name: Name of the S3 bucket
        key: S3 object key (file path)
        
    Returns:
        dict: The persona data, or empty dict if not found
    """
    s3_client = get_s3_client()
    
    try:
        response = s3_client.get_object(Bucket=bucket_name, Key=key)
        persona_data = json.loads(response["Body"].read())
        return persona_data
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            print(f"📄 File {key} not found in bucket {bucket_name}")
            return {}
        else:
            print(f"❌ Error retrieving {key} from {bucket_name}: {e}")
            raise

def save_persona_to_s3(bucket_name: str, key: str, persona_data: dict) -> bool:
    """
    Saves a persona JSON file to S3.
    
    Args:
        bucket_name: Name of the S3 bucket
        key: S3 object key (file path)
        persona_data: The persona data to save
        
    Returns:
        bool: True if successful, False otherwise
    """
    s3_client = get_s3_client()
    
    try:
        s3_client.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=json.dumps(persona_data, indent=2),
            ContentType='application/json'
        )
        print(f"✅ Successfully saved {key} to {bucket_name}")
        return True
    except ClientError as e:
        print(f"❌ Error saving {key} to {bucket_name}: {e}")
        return False

def create_default_traveler_persona(customer_id: str, username: str) -> dict:
    """
    Creates a default traveler persona JSON structure.
    
    Args:
        customer_id: The customer's unique identifier
        username: The customer's username
        
    Returns:
        dict: Default traveler persona structure
    """
    return {
        "customerId": customer_id,
        "version": "1.0",
        "lastUpdated": datetime.utcnow().isoformat() + "Z",
        "demographics": {
            "firstName": "",
            "lastName": "",
            "DOB": "",
            "sex": "",
            "hometown": {
                "city": "",
                "country": ""
            }
        },
        "travel_persona": {
            "travel_companions": [],
            "preferences": {
                "vibe": "",
                "focus": "",
                "pace": "",
                "authenticity": "",
                "social_style": ""
            },
            "habits": {
                "spending": "",
                "interests": []
            },
            "trips": {}
        }
    }
