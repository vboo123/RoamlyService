import os
import json
import hashlib
import asyncio
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

# === Load semantic config ===
with open("semantic_config.json", "r") as f:
    semantic_config = json.load(f)

def get_relevant_keys(landmark_type):
    return semantic_config.get(landmark_type, ["origin.general", "media.references"])

# === Data Inputs ===
with open("landmarks.json", "r") as f:
    landmark_objs = json.load(f)

interests = [
    'Nature', 'History', 'Food', 'Museums',
    'Adventure', 'Beaches', 'Architecture', 'Fitness',
    'Travel', 'Technology'
]
languages = ["English"]
countries = ["United States", "India", "Mexico"]

interest_mapping = {
    "Nature": "Nature",
    "History": "History",
    "Food": "Food",
    "Museums": "Museums",
    "Adventure": "Exploration",
    "Beaches": "Beaches",
    "Architecture": "Architecture",
    "Fitness": "Fitness",
    "Travel": "Travel",
    "Technology": "Technology"
}

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

def insert_semantic_response(landmark, semantic_key, question, response, country, interest=None, mapped_category=None):
    # Prepare and upload JSON
    response_data = {
        "landmark": landmark,
        "semantic_key": semantic_key,
        "country": country,
        "interest": interest,
        "mapped_category": mapped_category,
        "question": question,
        "response": response
    }

    safe_landmark = sanitize_filename(landmark)
    safe_key = sanitize_filename(semantic_key)
    safe_country = sanitize_filename(country)
    safe_interest = sanitize_filename(interest) if interest else "general"

    filename = f"{safe_landmark}_{safe_key}_{safe_country}_{safe_interest}.json"
    s3_key = f"semantic_responses/{filename}"

    json_url = upload_json_to_s3(response_data, s3_key)

    # Store reference in DynamoDB
    item = {
        "landmark_id": landmark.replace(" ", "_"),
        "semantic_country_key": f"{semantic_key}#{country}#{interest}",
        "semantic_key": semantic_key,
        "user_country": country,
        "json_url": json_url
    }
    if interest:
        item["user_interest"] = interest
        item["mapped_category"] = mapped_category

    semantic_table.put_item(Item=item)
    print(f"✅ Inserted semantic key reference: {semantic_key} ({country})")

async def generate_and_store_semantics(landmark_obj):
    landmark = landmark_obj["name"]
    landmark_type = landmark_obj["type"]
    city = landmark_obj.get("city", "a city")

    semantic_keys = get_relevant_keys(landmark_type)
    for key in semantic_keys:
        for country in countries:
            for interest in interests:
                mapped_category = interest_mapping.get(interest, "curiosity")

                template = semantic_config.get(landmark_type, {}).get(key)
                if not template:
                    print(f"⚠️ Skipping missing prompt for {landmark_type} → {key}")
                    continue

                prompt = template.format(
                    city=city,
                    country=country,
                    userCountry=country,
                    mappedCategory=mapped_category,
                    landmark=landmark
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
                    insert_semantic_response(landmark, key, prompt, response, country, interest, mapped_category)
                except Exception as e:
                    print(f"❌ Failed to generate OpenAI response for {key}: {e}")

async def main():
    for landmark_obj in landmark_objs:
        insert_landmark_metadata(landmark_obj)
        await generate_and_store_semantics(landmark_obj)

if __name__ == "__main__":
    asyncio.run(main())
