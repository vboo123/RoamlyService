# === assemble_response.py ===
import boto3
import json
import os
from dotenv import load_dotenv
from boto3.dynamodb.conditions import Key

# Load environment
load_dotenv()

# Setup DynamoDB
dynamodb = boto3.resource(
    'dynamodb',
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name="us-east-1"
)
semantic_table = dynamodb.Table("semantic_responses")

# Determine absolute path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Load semantic key config
with open(os.path.join(BASE_DIR, "semantic_config.json"), "r") as f:
    semantic_config = json.load(f)

# Load valid interests
with open(os.path.join(BASE_DIR, "interests.json"), "r") as f:
    interest_data = json.load(f)
valid_interests = set(interest_data.get("interests", []))

def get_relevant_keys(landmark_type):
    return semantic_config.get(landmark_type, ["origin.general", "media.references"])

def assemble_response(
    landmark_id: str,
    landmark_type: str,
    user_country: str = "default",
    interest: str = "default"
) -> str:
    semantic_keys = get_relevant_keys(landmark_type.lower())
    facts = {}

    for key in semantic_keys:
        try:
            full_key = f"{key}#{user_country}#{interest}"
            print(f"🔍 Trying to query: landmark_id={landmark_id}, semantic_country_key={full_key}")

            response = semantic_table.query(
                KeyConditionExpression=Key("landmark_id").eq(landmark_id) & Key("semantic_country_key").eq(full_key)
            )

            items = response.get("Items", [])
            print(f"✅ Query returned {len(items)} items")

            if items:
                facts[key] = items[0]["response"]
                continue

            fallback_key = f"{key}#default#default"
            fallback = semantic_table.query(
                KeyConditionExpression=Key("landmark_id").eq(landmark_id) & Key("semantic_country_key").eq(fallback_key)
            )
            fallback_items = fallback.get("Items", [])
            if fallback_items:
                facts[key] = fallback_items[0]["response"]
        except Exception as e:
            print(f"❌ Error fetching key {key}: {e}")

    assembled = f"Hey there! Welcome to the {landmark_id.replace('_', ' ')}. "
    for key in semantic_keys:
        if facts.get(key):
            assembled += facts[key] + " "

    return assembled.strip()
