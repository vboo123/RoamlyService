# === updated_batch_script.py ===
import os
import json
import hashlib
import asyncio
from itertools import combinations
from dotenv import load_dotenv
from geopy.geocoders import Nominatim
from geolib import geohash
import boto3
import openai
from google.cloud import texttospeech

# === Load .env ===
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# === AWS Setup ===
dynamodb = boto3.resource(
    'dynamodb',
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name='us-east-1'
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
AUDIO_URL_BASE = os.getenv("AUDIO_URL_BASE")
AUDIO_DIR = "audio"
os.makedirs(AUDIO_DIR, exist_ok=True)

TTS_CLIENT = texttospeech.TextToSpeechClient()

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

def get_coordinates(place):
    geolocator = Nominatim(user_agent="roamly_app")
    location = geolocator.geocode(place)
    return (location.latitude, location.longitude) if location else (None, None)

def upload_to_s3(local_path: str, s3_key: str):
    s3_client.upload_file(
        local_path,
        S3_BUCKET,
        s3_key,
        ExtraArgs={"ContentType": "audio/mpeg"}
    )

def generate_mp3_if_missing(text: str) -> str:
    text_hash = hashlib.md5(text.encode()).hexdigest()
    filename = f"{text_hash}.mp3"
    local_path = os.path.join(AUDIO_DIR, filename)
    s3_key = f"audio/{filename}"
    audio_url = AUDIO_URL_BASE + filename

    if not os.path.exists(local_path):
        synthesis_input = texttospeech.SynthesisInput(text=text)
        voice = texttospeech.VoiceSelectionParams(
            language_code="en-US",
            name="en-US-Wavenet-D",
            ssml_gender=texttospeech.SsmlVoiceGender.MALE
        )
        audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
        response = TTS_CLIENT.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)
        with open(local_path, "wb") as out:
            out.write(response.audio_content)

    try:
        upload_to_s3(local_path, s3_key)
    except Exception as e:
        print(f"⚠️ Failed to upload audio: {e}")

    return audio_url

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

def insert_semantic_response(landmark, semantic_key, question, response, country):
    audio_url = generate_mp3_if_missing(response)
    item = {
        "landmark_id": landmark.replace(" ", "_"),
        "semantic_key": semantic_key,
        "user_country": country,
        "query": question,
        "response": response,
        "audio_url": audio_url
    }
    semantic_table.put_item(Item=item)
    print(f"✅ Inserted semantic key: {semantic_key} ({country})")

async def generate_and_store_semantics(landmark, landmark_type):
    semantic_keys = get_relevant_keys(landmark_type)
    for key in semantic_keys:
        for country in countries + ["default"]:
            prompt = (
                f"You are a local tour guide. A tourist asks about '{key}'.\n"
                f"They are visiting the {landmark} from {country}.\n"
                f"Respond warmly, like a narrator."
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
                insert_semantic_response(landmark, key, prompt, response, country)
            except Exception as e:
                print(f"❌ Failed to generate OpenAI response for {key}: {e}")

async def main():
    for landmark_obj in landmark_objs:
        insert_landmark_metadata(landmark_obj)
        await generate_and_store_semantics(landmark_obj["name"], landmark_obj["type"])

if __name__ == "__main__":
    asyncio.run(main())