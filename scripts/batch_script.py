import asyncio
import os
import json
import sys
import hashlib
from dotenv import load_dotenv
from itertools import combinations, product
from cassandra.cluster import Cluster
from geopy.geocoders import Nominatim
from geolib import geohash
from gpt4all import GPT4All
from google.cloud import texttospeech
import boto3

load_dotenv()

# === Google TTS Client ===
TTS_CLIENT = texttospeech.TextToSpeechClient()
AUDIO_DIR = "audio"
os.makedirs(AUDIO_DIR, exist_ok=True)
AUDIO_URL_BASE = os.getenv("AUDIO_URL_BASE")  # e.g., https://roamly-audio.s3.us-west-1.amazonaws.com/audio/

# === AWS S3 Client ===
s3_client = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION")
)
S3_BUCKET = os.getenv("S3_BUCKET_NAME")

# === Cassandra Setup ===
cluster = Cluster(['127.0.0.1'])
session = cluster.connect()
session.set_keyspace('roamly_keyspace')

# === Inputs ===
with open("./landmarks.json", "r") as f:
    landmarks = json.load(f)

interests = [
    "Technology", "Travel", "Fitness"
]
languages = ["English"]
ages = ["young"]
formats = ["medium"]
countries = ["United States"]

def get_combos():
    return product(
        languages,
        combinations(interests, 3),
        ages,
        formats,
        countries
    )

def generate_key(landmark, interest_combo, language, age, format, country):
    interest_str = ",".join(sorted(interest_combo))
    combo_string = f"{landmark}|{interest_str}|{language}|{age}|{format}|{country}"
    print(f"🧩 Key String: {combo_string}")
    return hashlib.md5(combo_string.encode()).hexdigest()

def generate_prompt(landmark, interest_combo, language, age, format, country):
    return f"""
        Can you provide a lively, narrative-style history of {landmark} with engaging storytelling, fun facts, recent events, and tourist-friendly tips, especially tailored for an audience from {country} 
        who speaks {language} and is interested in {interest_combo[0]}, {interest_combo[1]}, and {interest_combo[2]}?
        Include references to popular culture from that country or region. Keep it casual, friendly, and informative, written in a way that's easy to read out loud.
        Make sure to touch on:
        - Cost/financial history
        - Architectural details
        - Key political or social events
        - Who owns and maintains it today
        Weave everything into one flowing story without headers or bullet points. This is for a {age} audience and should be a {format}-length response.
        """.strip()

def get_coordinates(location):
    geolocator = Nominatim(user_agent="roamly_app")
    loc = geolocator.geocode(location)
    return (loc.latitude, loc.longitude) if loc else (None, None)

def create_or_update_property(landmark, json_string):
    address = f"{landmark}"
    lat, lon = get_coordinates(address)
    if not lat or not lon:
        print(f"Could not locate coordinates for {landmark}")
        return

    # Reverse geocode to get city and country
    geolocator = Nominatim(user_agent="roamly_app")
    location = geolocator.reverse((lat, lon), exactly_one=True)
    city = location.raw['address'].get('city') or location.raw['address'].get('town') or location.raw['address'].get('village') or "Unknown"
    country = location.raw['address'].get('country', "Unknown")

    geohash_code = geohash.encode(lat, lon, precision=2)

    session.execute("""
        CREATE TABLE IF NOT EXISTS properties (
            geoHash TEXT,
            latitude TEXT,
            longitude TEXT,
            landmarkName TEXT,
            country TEXT,
            city TEXT,
            responses TEXT,
            PRIMARY KEY ((geoHash), landmarkName)
        );
    """)

    session.execute("""
        INSERT INTO properties (
            geoHash, latitude, longitude, landmarkName, country, city, responses
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (
        geohash_code, str(lat), str(lon), landmark,
        country, city, json_string
    ))

    print(f"✅ Inserted {landmark} @ {city}, {country}")

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

    if os.path.exists(local_path):
        print(f"✅ Audio already exists locally: {filename}")
    else:
        # Call Google TTS
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
            print(f"🎧 Saved locally: {filename}")

    try:
        upload_to_s3(local_path, s3_key)
        print(f"☁️ Uploaded to S3: {audio_url}")
    except Exception as e:
        print(f"⚠️ S3 upload failed: {e}")

    return audio_url

async def generate_narrations(landmark):
    responses = {}
    model = GPT4All(model_name='Meta-Llama-3-8B-Instruct.Q4_0.gguf', allow_download=False)

    for lang, interest_combo, age, fmt, country in get_combos():
        key = generate_key(landmark, interest_combo, lang, age, fmt, country)
        if key in responses:
            continue

        prompt = generate_prompt(landmark, interest_combo, lang, age, fmt, country)
        print(f"\n\n▶ Generating for: {key}...\nPrompt:\n{prompt}\n")

        narration_text = ""
        for token in model.generate(prompt, streaming=True):
            narration_text += token
            sys.stdout.write(token)
        sys.stdout.flush()

        responses[key] = {
            "text": narration_text.strip(),
            "audio_url": generate_mp3_if_missing(narration_text.strip())
        }

    json_string = json.dumps(responses, indent=4)
    create_or_update_property(landmark, json_string)
    print(f"\n✅ Completed generation for {landmark}")

async def main():
    for landmark in landmarks:
        await generate_narrations(landmark)

if __name__ == "__main__":
    asyncio.run(main())
