from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from geolib import geohash
from boto3.dynamodb.conditions import Attr
import boto3
import uuid
import json
import hashlib
import os
import traceback
from dotenv import load_dotenv
import decimal
from scripts.assembleResponse import assemble_response

# === Load environment variables ===
load_dotenv()

# === Setup DynamoDB ===
dynamodb = boto3.resource(
    'dynamodb',
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name="us-east-2"
)
landmarks_table = dynamodb.Table("Landmarks")
users_table = dynamodb.Table("Users")

# === FastAPI app ===
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    age: str
    language: str

@app.post("/register-user/")
async def register_user(user: User):
    try:
        user_id = str(uuid.uuid4())
        users_table.put_item(Item={
            "email": user.email,
            "name": user.name,
            "user_id": user_id,
            "country": user.country,
            "interestOne": user.interestOne,
            "age": user.age,
            "language": user.language
        })
        return {"message": "User registered successfully", "user_id": user_id}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to register user: {e}")

@app.get("/login/")
async def login_user(name: str = Query(...), email: str = Query(...)):
    try:
        result = users_table.get_item(Key={"email": email})
        user = result.get("Item")
        if not user or user.get("name") != name:
            raise HTTPException(status_code=404, detail="User not found")
        return convert_dynamodb_types(user)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Login failed: {e}")

@app.get("/get-properties/")
async def get_properties(
    lat: float, long: float,
    interestOne: str,
    userAge: str, userCountry: str, userLanguage: str
):
    try:
        geohash_code = geohash.encode(lat, long, precision=6)
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
                f"{landmark_name}_{interestOne}_{userCountry}_{userLanguage}_{age_group}_small",
                f"{landmark_name}_{interestOne}_{userCountry}_{userLanguage}_{age_group}_middle",
                f"{landmark_name}_{interestOne}_{userCountry}_{userLanguage}_{age_group}_large"
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

@app.get("/landmark-response/")
async def get_landmark_response(
    landmark: str,
    userCountry: str = "default",
    interestOne: str = "",
    semanticKey: str = "origin.general"
):
    try:
        # Normalize input
        landmark_id = landmark.replace(" ", "_")

        # Normalize country mapping
        country_map = {
            "UnitedStatesofAmerica": "United States",
            "USA": "United States",
            "US": "United States"
        }
        userCountry = country_map.get(userCountry, userCountry)

        # Compose key dynamically based on semanticKey
        semantic_country_key = f"{semanticKey}#{userCountry}#{interestOne}"

        # Query the semantic_responses table
        semantic_table = dynamodb.Table("semantic_responses")
        response = semantic_table.get_item(
            Key={
                "landmark_id": landmark_id,
                "semantic_country_key": semantic_country_key
            }
        )

        print(response)

        item = response.get("Item")
        if not item:
            raise HTTPException(status_code=404, detail="No semantic response found")

        return {
            "landmark": landmark_id,
            "semantic_key": semanticKey,
            "country": userCountry,
            "interest": interestOne,
            "json_url": item["json_url"],
        }

    except Exception as e:
        print("🔥 ERROR in /landmark-response:", e)
        raise HTTPException(status_code=500, detail=f"Failed to fetch semantic response: {str(e)}")
