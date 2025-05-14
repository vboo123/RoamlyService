# === assemble_response.py ===
import boto3
import json
import os
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Setup DynamoDB
dynamodb = boto3.resource(
    'dynamodb',
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION")
)
semantic_table = dynamodb.Table("semantic_responses")

# Load semantic key config
with open("semantic_config.json", "r") as f:
    semantic_config = json.load(f)

def get_relevant_keys(landmark_type):
    return semantic_config.get(landmark_type, ["origin.general", "media.references"])

def assemble_response(landmark_id: str, landmark_type: str, user_country: str = "default", interests: list = None) -> str:
    semantic_keys = get_relevant_keys(landmark_type)
    facts = {}

    for key in semantic_keys:
        try:
            result = semantic_table.get_item(Key={
                "landmark_id": landmark_id,
                "semantic_key": key
            })
            item = result.get("Item")
            if item and item.get("user_country") == user_country:
                facts[key] = item["response"]
            elif item and item.get("user_country") == "default":
                facts[key] = item["response"]
        except Exception as e:
            print(f"Error fetching key {key}: {e}")

    interest_phrase = ""
    if interests:
        if "Movies" in interests or "TV" in interests:
            interest_phrase = "If you're into films, you'll especially love this spot! "
        elif "Photography" in interests:
            interest_phrase = "It’s also a favorite for photographers. "
        elif "History" in interests:
            interest_phrase = "Its long history makes it a must-see. "

    assembled = f"Hey there! Welcome to the {landmark_id}. " + interest_phrase
    for key in semantic_keys:
        if facts.get(key):
            assembled += facts[key] + " "

    return assembled.strip()
