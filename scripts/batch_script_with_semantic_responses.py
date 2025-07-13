import os
import json
import hashlib
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from geopy.geocoders import Nominatim
from geolib import geohash
import boto3
import openai

# ---- Setup ----
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

dynamodb = boto3.resource(
    'dynamodb',
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name='us-east-2'
)
semantic_table = dynamodb.Table("semantic_responses")
landmark_table = dynamodb.Table("Landmarks")

s3_client = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION")
)
S3_BUCKET = os.getenv("S3_BUCKET_NAME")
S3_URL_BASE = os.getenv("S3_URL_BASE")

def create_semantic_responses_table_if_not_exists():
    """Create semantic_responses table if it doesn't exist"""
    try:
        # Try to describe the table to see if it exists
        semantic_table.load()
        print("✅ Semantic_responses table already exists")
    except Exception as e:
        if "ResourceNotFoundException" in str(e):
            print("🔄 Creating semantic_responses table...")
            
            # Create the table
            table = dynamodb.create_table(
                TableName='semantic_responses',
                KeySchema=[
                    {
                        'AttributeName': 'landmark_id',
                        'KeyType': 'HASH'  # Partition key
                    },
                    {
                        'AttributeName': 'semantic_key',
                        'KeyType': 'RANGE'  # Sort key
                    }
                ],
                AttributeDefinitions=[
                    {
                        'AttributeName': 'landmark_id',
                        'AttributeType': 'S'
                    },
                    {
                        'AttributeName': 'semantic_key',
                        'AttributeType': 'S'
                    }
                ],
                BillingMode='PAY_PER_REQUEST'  # On-demand billing
            )
            
            # Wait for table to be created
            table.meta.client.get_waiter('table_exists').wait(TableName='semantic_responses')
            print("✅ Semantic_responses table created successfully")
        else:
            print(f"❌ Error checking/creating table: {e}")
            raise e

# === Load semantic config ===
with open("semantic_config.json", "r") as f:
    semantic_config = json.load(f)

def get_relevant_keys(landmark_type):
    return semantic_config.get(landmark_type, ["origin.general", "media.references"])

# === Data Inputs ===
with open("landmarks.json", "r") as f:
    landmark_objs = json.load(f)

# Simplified categories - no more interest mapping needed
categories = [
    'Nature', 'Technology', 'Fitness'
]
languages = ["English"]
countries = ["United States", "India"]
age_groups = ["young", "old"]

def get_coordinates(place):
    geolocator = Nominatim(user_agent="roamly_app")
    location = geolocator.geocode(place)
    return (location.latitude, location.longitude) if location else (None, None)

def upload_json_to_s3(data: dict, s3_key: str) -> str:
    local_path = os.path.join("/tmp", s3_key.split("/")[-1])
    with open(local_path, "w") as f:
        json.dump(data, f)
    s3_client.upload_file(
        local_path,
        S3_BUCKET,
        s3_key,
        ExtraArgs={"ContentType": "application/json"}
    )
    return S3_URL_BASE + s3_key

def insert_landmark_metadata(landmark_obj):
    name = landmark_obj["name"]
    landmark_type = landmark_obj.get("type", "unknown")
    lat, lon = get_coordinates(name)
    if not lat or not lon:
        print(f"❌ Skipping {name} due to missing coordinates")
        return

    geohash_code = geohash.encode(lat, lon, precision=6)
    landmark_table.put_item(Item={
        "landmark_id": name.replace(" ", "_"),
        "name": name,
        "type": landmark_type,
        "coordinates": {"lat": str(lat), "lng": str(lon)},
        "geohash": geohash_code
    })
    print(f"✅ Inserted landmark metadata for {name}")

def sanitize_filename(s: str) -> str:
    return s.replace(" ", "_").replace("/", "_").lower()

def insert_consolidated_semantic_response(landmark, semantic_key, consolidated_data):
    """Insert consolidated semantic response with new structure"""
    safe_landmark = sanitize_filename(landmark)
    safe_key = sanitize_filename(semantic_key)
    
    filename = f"{safe_landmark}_{safe_key}.json"
    s3_key = f"semantic_responses/{filename}"
    
    json_url = upload_json_to_s3(consolidated_data, s3_key)
    
    # Store reference in DynamoDB with simplified structure
    item = {
        "landmark_id": landmark.replace(" ", "_"),
        "semantic_key": semantic_key,
        "json_url": json_url
    }
    
    semantic_table.put_item(Item=item)
    print(f"✅ Inserted consolidated semantic response: {semantic_key} for {landmark}")

async def generate_and_store_consolidated_semantics(landmark_obj):
    landmark = landmark_obj["name"]
    landmark_type = landmark_obj["type"]
    city = landmark_obj.get("city", "a city")

    semantic_keys = get_relevant_keys(landmark_type)
    
    for semantic_key in semantic_keys:
        print(f"🔄 Generating responses for {landmark} - {semantic_key}")
        
        # Initialize consolidated data structure
        consolidated_data = {
            "landmark": landmark,
            "semantic_key": semantic_key,
            "responses": [],
            "extracted_details": {},
            "specific_Youtubes": {},
            "last_updated_utc": datetime.utcnow().isoformat() + "Z"
        }
        
        # Generate responses for all combinations
        for country in countries:
            for category in categories:
                for age_group in age_groups:
                    template = semantic_config.get(landmark_type, {}).get(semantic_key)
                    if not template:
                        print(f"⚠️ Skipping missing prompt for {landmark_type} → {semantic_key}")
                        continue

                    prompt = template.format(
                        city=city,
                        country=country,
                        userCountry=country,
                        mappedCategory=category,  # Use category directly, no mapping needed
                        landmark=landmark,
                        age_group=age_group
                    )

                    try:
                        completion = openai.ChatCompletion.create(
                            model="gpt-3.5-turbo",
                            messages=[
                                {"role": "system", "content": "You are a friendly and knowledgeable travel guide."},
                                {"role": "user", "content": prompt}
                            ],
                            temperature=0.7,
                            max_tokens=500
                        )
                        response = completion['choices'][0]['message']['content'].strip()
                        
                        # Add to responses array
                        consolidated_data["responses"].append({
                            "user_country": country,
                            "user_age": age_group,
                            "mapped_category": category,  # Use category directly
                            "response": response
                        })
                        
                        print(f"✅ Generated response for {country}/{category}/{age_group}")
                        
                    except Exception as e:
                        print(f"❌ Failed to generate OpenAI response for {semantic_key}: {e}")
        
        # Store the consolidated response
        insert_consolidated_semantic_response(landmark, semantic_key, consolidated_data)

async def main():
    # Create table if it doesn't exist
    create_semantic_responses_table_if_not_exists()
    
    for landmark_obj in landmark_objs:
        insert_landmark_metadata(landmark_obj)
        await generate_and_store_consolidated_semantics(landmark_obj)

if __name__ == "__main__":
    asyncio.run(main())
