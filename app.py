from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from geolib import geohash
from cassandra.cluster import Cluster
from cassandra.query import dict_factory
from boto3.dynamodb.conditions import Attr
import boto3
import uuid
import json
import hashlib
import os
import traceback
from dotenv import load_dotenv
import decimal

# === Load environment variables ===
load_dotenv()

# === Setup DynamoDB ===
dynamodb = boto3.resource(
    'dynamodb',
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name="us-east-1"  # Hardcoded for now
)
landmarks_table = dynamodb.Table("Landmarks")

# === Setup Cassandra for user info ===
cluster = Cluster(['127.0.0.1'])
session = cluster.connect()
session.set_keyspace('roamly_keyspace')

# === FastAPI app ===
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

import decimal

def convert_dynamodb_types(obj):
    if isinstance(obj, list):
        return [convert_dynamodb_types(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: convert_dynamodb_types(v) for k, v in obj.items()}
    elif isinstance(obj, decimal.Decimal):
        return float(obj) if "." in str(obj) else int(obj)
    return obj


class User(BaseModel):
    name: str
    email: str
    country: str
    interestOne: str
    interestTwo: str
    interestThree: str
    age: str
    language: str

@app.post("/register-user/")
async def register_user(user: User):
    try:
        user_id = uuid.uuid4()
        session.execute("""
            INSERT INTO users (user_id, name, email, country, interestOne, interestTwo, interestThree, age, language)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            user_id, user.name, user.email, user.country,
            user.interestOne, user.interestTwo, user.interestThree,
            user.age, user.language
        ))
        return {"message": "User registered successfully", "user_id": str(user_id)}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to register user: {e}")

@app.get("/login/")
async def login_user(name: str = Query(...), email: str = Query(...)):
    try:
        row = session.execute("SELECT * FROM users WHERE name = %s AND email = %s ALLOW FILTERING", (name, email)).one()
        if row:
            return {
                "user_id": row.user_id,
                "name": row.name,
                "email": row.email,
                "country": row.country,
                "interestOne": row.interestone,
                "interestTwo": row.interesttwo,
                "interestThree": row.interestthree,
                "age": row.age,
                "language": row.language
            }
        else:
            raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Login failed: {e}")

@app.get("/get-properties/")
async def get_properties(
    lat: float, long: float,
    interestOne: str, interestTwo: str, interestThree: str,
    userAge: str, userCountry: str, userLanguage: str
):
    try:
        geohash_code = geohash.encode(lat, long, precision=2)
        print("Query geohash:", geohash_code)

        scan_results = landmarks_table.scan(
            FilterExpression=Attr("geohash").eq(geohash_code)
        )

        classify_age = lambda age: "young" if age < 30 else "middleage" if age <= 60 else "old"
        age_group = classify_age(int(userAge))

        properties = []
        for item in scan_results.get("Items", []):
            landmark_name = item["landmark_id"]

            keys_to_extract = [
                f"{landmark_name}_{interestOne}_{interestTwo}_{interestThree}_{userCountry}_{userLanguage}_{age_group}_small",
                f"{landmark_name}_{interestOne}_{interestTwo}_{interestThree}_{userCountry}_{userLanguage}_{age_group}_middle",
                f"{landmark_name}_{interestOne}_{interestTwo}_{interestThree}_{userCountry}_{userLanguage}_{age_group}_large"
            ]

            responses_data = item.get("responses", {})
            filtered_responses = {key: responses_data.get(key) for key in keys_to_extract if key in responses_data}

            properties.append({
                "geohash": item.get("geohash"),
                "latitude": item["coordinates"]["lat"],
                "longitude": item["coordinates"]["lng"],
                "landmarkName": landmark_name,
                "city": item.get("city"),
                "country": item.get("country"),
                "responses": filtered_responses,
            })

        if not properties:
            return {"message": "No landmarks found near you.", "properties": []}

        return {"properties": properties}

    except Exception as e:
        print("🔥 ERROR in /get-properties:", e)
        raise HTTPException(status_code=500, detail=f"DynamoDB query failed: {str(e)}")

@app.get("/landmark-response")
async def get_landmark_response(
    landmark: str,
    geohash: str,
    userCountry: str = "default",
    interestOne: str = "",
    interestTwo: str = "",
    interestThree: str = ""
):
    country_map = {
        "UnitedStatesofAmerica": "United States",
        "USA": "United States",
        "US": "United States"
    }
    userCountry = country_map.get(userCountry, userCountry)

    interest_combo = sorted([interestOne, interestTwo, interestThree])
    interest_str = ",".join(interest_combo)
    normalized_landmark = landmark.replace("_", " ")
    key_string = f"{normalized_landmark}|{interest_str}|English|young|medium|{userCountry}"
    print("Key string used to generate hash:", key_string)
    response_key = hashlib.md5(key_string.encode()).hexdigest()
    print("Computed response_key:", response_key)

    try:
        result = landmarks_table.get_item(Key={
            "landmark_id": landmark.replace(" ", "_"),
            "geohash": geohash 
        })
        item = result.get("Item")
        if not item:
            raise HTTPException(status_code=404, detail="Landmark not found")

        responses = item.get("responses", {})
        if response_key not in responses:
            raise HTTPException(status_code=404, detail="No matching response found")

        return convert_dynamodb_types({
            "landmark": landmark,
            "country": userCountry,
            "text": responses[response_key]["text"],
            "audio_url": responses[response_key]["audio_url"]
        })

    except Exception as e:
        print("🔥 ERROR in /landmark-response:", e)
        raise HTTPException(status_code=500, detail=f"Error fetching from DynamoDB: {str(e)}")
