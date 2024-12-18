import asyncio
from openai import OpenAI
import os
from dotenv import load_dotenv
from itertools import combinations, product
from cassandra.cluster import Cluster
import json
from geolib import geohash
from geopy.geocoders import Nominatim

# Load environment variables
load_dotenv()

# Connect to the local Cassandra cluster
cluster = Cluster(['127.0.0.1'])  # Localhost
session = cluster.connect()

# Use the keyspace
session.set_keyspace('roamly_keyspace')

# OpenAI API setup
# api_key = os.getenv("OPENAI_API_KEY")
api_key = "sds"
client = OpenAI(api_key=api_key)

# Data inputs
languages = ["English"]
# languages = ["English", "Mandarin", "Hindi", "Spanish", "French", "Standard Arabic", "Bengali", "Russian", "Portuguese", "Urdu"]
interests = [
    "Drawing", 
    "Running", "Acting"
]
# interests = [
#     "Drawing", "Writing", "Photography", "Crafting", "Music", "Acting",
#     "Running", "Yoga", "Cycling", "Weightlifting", "Sports",
#     "Reading", "Movies/TV Shows", "Gaming", "Cooking",
#     "Traveling", "Food Tasting",
#     "Mathematics", "Learning Science",
#     "Volunteering"
# ]
ages = ["young", "middle age", "old"]
formats = ["small", "medium", "large"]
countries = ["United States of America"]
landmarks = ["Hollywood Sign"]

# Generate combinations of interests (3 at a time), languages, ages, formats
interest_combinations = combinations(interests, 3)
age_combinations = ages
format_combinations = formats
language_combinations = languages
country_combinations = countries
landmark_combinations = landmarks

def check_landmark_exists(landmark):
    # Create the properties table if it doesn't exist
    create_table_query = """
        CREATE TABLE IF NOT EXISTS properties (
            geoHash TEXT,
            landmarkName TEXT,
            country TEXT,
            city TEXT,
            responses TEXT,
            PRIMARY KEY ((geoHash), landmarkName)
        );
    """
    session.execute(create_table_query)
    index_query = "CREATE INDEX IF NOT EXISTS landmarkName_index ON properties (landmarkName);"
    session.execute(index_query)
    query = "SELECT responses FROM properties WHERE landmarkName = %s"
    rows = session.execute(query, (landmark,))
    
    for row in rows:
        if row:
            return row.responses
    return None

# Function to generate prompt and get response from OpenAI API
def generate_prompt_and_get_response(interest_combo, language, age, format, country, landmark):
    prompt = f"Can you provide a lively, narrative-style history of {landmark} with engaging storytelling, fun facts, recent events, and tourist-friendly tips, especially tailored for an audience from {country} who speaks {language} and is interested in {interest_combo[0]}, {interest_combo[1]}, and {interest_combo[2]}? Include references to popular culture from that country or region to help engage them more. Keep it casual, friendly, and informative, and write in a way that's easy to read out loud. The story should touch on the cost or financial history behind {landmark}, architectural details, key political or social events that shaped its history, and information about who owns it now and how it is maintained or managed—all woven into one flowing, easy-to-read narrative without headers, bullet points, or sections. This should be tailored to a {age} audience and {format} response."
    
    # Make OpenAI API call
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={
         "type": "text"
        },
        temperature=1,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0
    )

    return response

import json
import os

def check_key_exists(key, responseJSONFile):
    # Check if the file exists
    if os.path.exists(responseJSONFile):
        with open(responseJSONFile, 'r') as file:
            try:
                # Load existing data
                existing_data = json.load(file)
            except json.JSONDecodeError:
                # If the file is empty or not a valid JSON, return False
                return False
        # Check if the key exists in the loaded JSON data
        return key in existing_data
    else:
        # If the file doesn't exist, return False
        return False

def update_json_file(responseJSONFile, key, response_content):
    """
    Update the JSON file with new data without overwriting the existing data.
    """
    # Check if the file exists
    if os.path.exists(responseJSONFile):
        with open(responseJSONFile, 'r') as file:
            try:
                # Load existing data
                existing_data = json.load(file)
            except json.JSONDecodeError:
                # In case the file is empty or not valid JSON
                existing_data = {}
    else:
        # If the file doesn't exist, initialize an empty dictionary
        existing_data = {}

    # Add the new response to the existing data
    existing_data[key] = response_content

    # Write the updated data back to the file
    with open(responseJSONFile, 'w') as file:
        json.dump(existing_data, file, indent=4)

async def populate_responses(landmark, responseJSONFile):
    # Iterate through all combinations and get responses
    for language, interest_combo, age, format, country in product(language_combinations, interest_combinations, age_combinations, format_combinations, country_combinations):
        key = f"{landmark.replace(' ', '')}_" \
              f"{interest_combo[0].replace(' ', '')}_" \
              f"{interest_combo[1].replace(' ', '')}_" \
              f"{interest_combo[2].replace(' ', '')}_" \
              f"{country.replace(' ', '')}_" \
              f"{language.replace(' ', '')}_" \
              f"{age.replace(' ', '')}_" \
              f"{format.replace(' ', '')}"
        
        # Check if the key already exists in the JSON file
        if not check_key_exists(key, responseJSONFile):
            # response = generate_prompt_and_get_response(interest_combo, language, age, format, country, landmark)
            response = "test response"

            # response_content = response.choices[0].message.content
            response_content = response

            update_json_file(responseJSONFile, key, response_content)
            print(response_content)  # Output the response
        else:
            print(f"Key already exists: {key}") 
        
    # Return the final JSON file content as a string to insert into the database
    with open(responseJSONFile, 'r') as file:
        try:
            # Load the JSON data
            response_data = json.load(file)
            # Convert the JSON object to a string
            response_data_str = json.dumps(response_data)
            return response_data_str
        except json.JSONDecodeError:
            return None

def get_coordinates(location):
    geolocator = Nominatim(user_agent="myApp")
    location_obj = geolocator.geocode(location)
    if location_obj:
        return location_obj.latitude, location_obj.longitude
    else:
        return None, None

# right now, need to manually set city name, but eventually, will automate this
def insert_cassandra_db(responseJSON, landmark):
     # delete responses.json
    os.remove("responses.json")
    if responseJSON:
        insert_query = """
                INSERT INTO properties (
                    geoHash, landmarkName, country, city, responses
                ) 
                VALUES (%s, %s, %s, %s, %s)"""
        # structure address = property.name + ", " + property.city
        address = landmark + ", " + "Los Angeles"
        lat, lon = get_coordinates(address)
        geohash_code = geohash.encode(lat, lon, precision=2)
        session.execute(insert_query, (
            geohash_code, landmark, "Los Angeles", "United States of America", responseJSON
        ))
    else:
        print("Error creating JSON file")

async def main():
    for landmark in landmarks:
        landmarkResponses = check_landmark_exists(landmark)
        if landmarkResponses is not None:
            # Check if landmarkResponses is a string and needs to be converted to JSON
            if isinstance(landmarkResponses, str):
                try:
                    landmarkResponses = json.loads(landmarkResponses)  # Convert string to JSON (dict/list)
                except json.JSONDecodeError:
                    print(f"Error: landmarkResponses for {landmark} is not valid JSON string.")
                    break  
            # Open the file for writing and update the content
            with open('responses.json', 'w') as file:
                json.dump(landmarkResponses, file, indent=4)
            responseJSON = await populate_responses(landmark, "responses.json")
            insert_cassandra_db(responseJSON, landmark)
        else:
            # create JSON file with responses, and then insert all the required values into the properties table
            responseJSON = await populate_responses(landmark, "responses.json")
            insert_cassandra_db(responseJSON, landmark)
           

if __name__ == "__main__":
    asyncio.run(main())