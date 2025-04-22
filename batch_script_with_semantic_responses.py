import asyncio
from openai import OpenAI
import os
from dotenv import load_dotenv
from itertools import combinations, product
from cassandra.cluster import Cluster
import json
from geolib import geohash
from geopy.geocoders import Nominatim
from gpt4all import GPT4All
import sys

# Load environment variables
load_dotenv()

# Connect to Cassandra
cluster = Cluster(['127.0.0.1'])
session = cluster.connect()
session.set_keyspace('roamly_keyspace')

# Data inputs
languages = ["English"]
interests = ["Technology"]
ages = ["young"]
countries = ["United States"]
landmarks = ["Hollywood Sign"]

interest_combinations = combinations(interests, 3)
followups_by_landmark = {
    "Hollywood Sign": {
        "height.general": "how tall is it?",
        "origin.general": "when was it built?",
        "media.references": "was it featured in any movies?"
    }
}

def insert_semantic_responses(property_id):
    create_table_query = """
    CREATE TABLE IF NOT EXISTS semantic_responses (
        property_id TEXT,
        semantic_key TEXT,
        query TEXT,
        response TEXT,
        user_country TEXT,
        PRIMARY KEY ((property_id, semantic_key), user_country)
    );
    """
    session.execute(create_table_query)

    if property_id not in followups_by_landmark:
        print(f"No follow-up mappings found for {property_id}")
        return

    model = GPT4All(model_name='Meta-Llama-3-8B-Instruct.Q4_0.gguf', allow_download=False)

    for semantic_key, question in followups_by_landmark[property_id].items():
        for country in ["default", "India"]:
            personalization = f" They are visiting from {country}." if country != "default" else ""
            prompt = f"""You are a local tour guide. A tourist asks: '{question}'\nThey are visiting the {property_id}.{personalization} Respond warmly, like a narrator.\nDo not include examples, instructions, or follow-up questions."""
            response = ""
            for token in model.generate(prompt, streaming=True):
                response += token
            session.execute("""
                INSERT INTO semantic_responses (property_id, semantic_key, query, response, user_country)
                VALUES (%s, %s, %s, %s, %s)
            """, (property_id, semantic_key, question, response.strip(), country))
            print(f"Inserted follow-up: {semantic_key} for {property_id} ({country})")

def get_coordinates(location):
    geolocator = Nominatim(user_agent="myApp")
    location_obj = geolocator.geocode(location)
    return (location_obj.latitude, location_obj.longitude) if location_obj else (None, None)

def insert_property(landmark):
    lat, lon = get_coordinates(f"{landmark}, Los Angeles")
    if not lat or not lon:
        print(f"Failed to get coordinates for {landmark}")
        return

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
    """
    )

    session.execute("""
        INSERT INTO properties (geoHash, latitude, longitude, landmarkName, country, city, responses)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (geohash_code, str(lat), str(lon), landmark, "United States of America", "Los Angeles", "{}"))
    print(f"Inserted landmark entry for {landmark}")

def assemble_response(property_id, user_country="default"):
    semantic_keys = ["origin.general", "height.general", "media.references"]
    facts = {}
    for key in semantic_keys:
        rows = session.execute("""
            SELECT response, user_country FROM semantic_responses
            WHERE property_id = %s AND semantic_key = %s ALLOW FILTERING
        """, (property_id, key))
        selected = ""
        for row in rows:
            if row.user_country == user_country:
                selected = row.response.strip()
                break
            elif row.user_country == "default" and not selected:
                selected = row.response.strip()
        facts[key] = selected

    template = (
        "Hey there! Welcome to the {landmark}. {origin} Fun fact: {height} "
        "Also, {media} Hope you're enjoying your trip!"
    )

    return template.format(
        landmark=property_id,
        origin=facts.get("origin.general", ""),
        height=facts.get("height.general", ""),
        media=facts.get("media.references", "")
    )

async def main():
    for landmark in landmarks:
        insert_property(landmark)
        insert_semantic_responses(landmark)
        for country in ["default", "India"]:
            response = assemble_response(landmark, user_country=country)
            print(f"\nAssembled Response for {country}:\n", response)

if __name__ == "__main__":
    asyncio.run(main())
