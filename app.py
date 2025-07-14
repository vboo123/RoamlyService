from fastapi import FastAPI, HTTPException, Query, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from boto3.dynamodb.conditions import Attr
import boto3
import uuid
import json
import os
import traceback
from dotenv import load_dotenv
import decimal
import requests
from services.audio_processing_service import audio_processing_service
from services.semantic_matching_service import semantic_matching_service
from typing import List
from utils.age_utils import AgeUtils
from endpoints.ask_landmark import ask_landmark_question

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
        # geohash_code = geohash.encode(lat, long, precision=6)
        geohash_code = "9q60vc"
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
                # "geohash": item.get("geohash"),
                "geohash": "9q60vc",
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
    interest: str = Query("Nature", alias="interest[]"),  # Handle the axios array format
    userCountry: str = "United States",
    semanticKey: str = "origin.general",
    age: int = 25
):
    """
    Get landmark response based on user criteria
    Args:
        landmark: Landmark name
        interest: Interest string (handles axios array format)
        userCountry: User's country (defaults to "United States")
        semanticKey: Semantic key to query (defaults to "origin.general")
        age: User's age as integer (defaults to 25)
    """
    try:
        print(f"🔍 landmark-response: {landmark}, {userCountry}, {interest}, {semanticKey}, {age}")
        
        # Normalize input
        landmark_id = landmark.replace(" ", "_")
        
        # Use interest directly since it's now a string
        user_interest = interest if interest else "Nature"
        
        # Classify age
        age_group = AgeUtils.classify_age(age)

        # Query the semantic_responses table
        semantic_table = dynamodb.Table("semantic_responses")
        response = semantic_table.get_item(
            Key={
                "landmark_id": landmark_id,
                "semantic_key": semanticKey
            }
        )

        item = response.get("Item")
        if not item:
            raise HTTPException(status_code=404, detail="No semantic response found")

        # Fetch the consolidated JSON from S3
        try:
            json_response = requests.get(item["json_url"], timeout=10)
            json_response.raise_for_status()
            json_data = json_response.json()
            
            # Find the specific response based on user criteria
            responses = json_data.get("responses", [])
            best_response = None
            
            # Look for exact match: country + category + age_group
            for resp in responses:
                if (resp.get("user_country") == userCountry and 
                    resp.get("mapped_category") == user_interest and
                    resp.get("user_age") == age_group):
                    best_response = resp["response"]
                    break
            
            # Fallback: try country + category match
            if not best_response:
                for resp in responses:
                    if (resp.get("user_country") == userCountry and 
                        resp.get("mapped_category") == user_interest):
                        best_response = resp["response"]
                        break
            
            # Fallback: try just country match
            if not best_response:
                for resp in responses:
                    if resp.get("user_country") == userCountry:
                        best_response = resp["response"]
                        break
            
            # Final fallback: use first available response
            if not best_response and responses:
                best_response = responses[0]["response"]
            
            return {
                "landmark": landmark_id,
                "semantic_key": semanticKey,
                "country": userCountry,
                "interest": user_interest,
                "age": age,
                "age_group": age_group,
                "response": best_response or "No response found",
                "json_url": item["json_url"],
                "extracted_details": json_data.get("extracted_details", {}),
                "specific_youtubes": json_data.get("specific_Youtubes", {})
            }
            
        except requests.RequestException as e:
            print(f"Failed to fetch response from S3: {e}")
            return {
                "landmark": landmark_id,
                "semantic_key": semanticKey,
                "country": userCountry,
                "interest": user_interest,
                "age": age,
                "age_group": age_group,
                "response": "Response content unavailable",
                "json_url": item["json_url"],
            }

    except Exception as e:
        print("🔥 ERROR in /landmark-response:", e)
        raise HTTPException(status_code=500, detail=f"Failed to fetch semantic response: {str(e)}")

class LandmarkQuestion(BaseModel):
    landmark: str
    question: str
    userCountry: str = "default"
    interestOne: str = ""

# Remove the old function - now using semantic_matching_service

@app.post("/ask-landmark")
async def ask_landmark_endpoint(
    landmark: str = Form(...),
    question: str = Form(None),
    userCountry: str = Form("United States"),
    interestOne: str = Form("Nature"),
    userId: str = Form(...),
    sessionId: str = Form(None),
    audio_file: UploadFile = File(None)
):
    """Wrapper for the ask-landmark functionality"""
    return await ask_landmark_question(
        landmark=landmark,
        question=question,
        userCountry=userCountry,
        interestOne=interestOne,
        userId=userId,
        sessionId=sessionId,
        audio_file=audio_file
    )
