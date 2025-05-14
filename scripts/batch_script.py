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
from google.cloud import texttospeech
import boto3
import openai


load_dotenv()


# === API Keys ===
openai.api_key = os.getenv("OPENAI_API_KEY")


# === DynamoDB Setup ===
dynamodb = boto3.resource(
   'dynamodb',
   aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
   aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
   region_name="us-east-1"
)
dynamo_table = dynamodb.Table("Landmarks")


# === Google TTS Client ===
TTS_CLIENT = texttospeech.TextToSpeechClient()
AUDIO_DIR = "audio"
os.makedirs(AUDIO_DIR, exist_ok=True)
AUDIO_URL_BASE = os.getenv("AUDIO_URL_BASE")


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
  'Nature',
  'History',
  'Food',
  'Museums',
  'Adventure',
  'Beaches',
  'Architecture',
  'Fitness',
  'Travel',
  'Technology',
]
languages = ["English", "Hindi"]
ages = ["young", "middleage", "old"]
formats = ["medium"]
countries = ["United States, India, Mexico"]


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


   geolocator = Nominatim(user_agent="roamly_app")
   location = geolocator.reverse((lat, lon), exactly_one=True)
   city = location.raw['address'].get('city') or location.raw['address'].get('town') or location.raw['address'].get('village') or "Unknown"
   country = location.raw['address'].get('country', "Unknown")
   geohash_code = geohash.encode(lat, lon, precision=6)


   responses_dict = json.loads(json_string)


   dynamo_table.put_item(Item={
       "landmark_id": landmark.replace(" ", "_"),
       "city": city,
       "country": country,
       "coordinates": {
           "lat": str(lat),
           "lng": str(lon)
       },
       "geohash": geohash_code,
       "responses": responses_dict
   })


   print(f"✅ Inserted into DynamoDB: {landmark} @ {city}, {country}")


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


   for lang, interest_combo, age, fmt, country in get_combos():
       key = generate_key(landmark, interest_combo, lang, age, fmt, country)
       if key in responses:
           continue


       prompt = generate_prompt(landmark, interest_combo, lang, age, fmt, country)
       print(f"\n▶ Generating for: {key}...\nPrompt:\n{prompt[:150]}...\n")


       try:
           response = openai.ChatCompletion.create(
               model="gpt-3.5-turbo",
               messages=[
                   {"role": "system", "content": "You are a friendly and informative travel guide."},
                   {"role": "user", "content": prompt}
               ],
               temperature=0.75,
               max_tokens=1000
           )
           narration_text = response['choices'][0]['message']['content'].strip()


           responses[key] = {
               "text": narration_text,
               "audio_url": generate_mp3_if_missing(narration_text)
           }


       except Exception as e:
           print(f"❌ Error generating narration for {landmark}: {e}")
           continue


   json_string = json.dumps(responses, indent=4)
   create_or_update_property(landmark, json_string)
   print(f"✅ Completed generation for {landmark}")


async def main():
   for landmark in landmarks:
       await generate_narrations(landmark)


if __name__ == "__main__":
   asyncio.run(main())



