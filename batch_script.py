from openai import OpenAI
import os
from dotenv import load_dotenv
from itertools import combinations, product
from cassandra.cluster import Cluster


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
            return True
    return False

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

for landmark in landmarks:
    landmarkExists = check_landmark_exists(landmark)
    if landmarkExists:
        print("landmark exists")
    else:
       print("landmark doesnt exist")

# # Iterate through all combinations and get responses
# for language, interest_combo, age, format, country, landmark in product(language_combinations, interest_combinations, age_combinations, format_combinations, country_combinations, landmark_combinations):
#     key = f"{landmark.replace(' ', '')}_" \
#         f"{interest_combo[0].replace(' ', '')}_" \
#         f"{interest_combo[1].replace(' ', '')}_" \
#         f"{interest_combo[2].replace(' ', '')}_" \
#         f"{country.replace(' ', '')}_" \
#         f"{language.replace(' ', '')}_" \
#         f"{age.replace(' ', '')}_" \
#         f"{format.replace(' ', '')}"
    
#     # Check if the key already exists
#     if not check_key_exists(key):
#         # Generate a prompt and get a response if the key does not exist
#         response = generate_prompt_and_get_response(interest_combo, language, age, format, country, landmark)

#         # Insert the key and its data into the properties table
#         insert_key(key, landmark, interest_combo, country, language, age, format)

#         print(response.choices[0].message.content)  # Output the response
#     else:
#         print(f"Key already exists: {key}") 