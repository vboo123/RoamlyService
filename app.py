from fastapi import FastAPI, HTTPException, Query, File, UploadFile, Form
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
import requests
from scripts.assembleResponse import assemble_response
from services.audio_processing_service import audio_processing_service
from services.semantic_matching_service import semantic_matching_service

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
    userCountry: str = "default",
    interestOne: str = "",
    semanticKey: str = "origin.general"
):
    try:
        print("🔍 landmark-response:", landmark, userCountry, interestOne, semanticKey)
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

        # Fetch the actual response content from S3
        try:
            json_response = requests.get(item["json_url"], timeout=10)
            json_response.raise_for_status()  # Raise an exception for bad status codes
            json_data = json_response.json()
            return {
                "landmark": landmark_id,
                "semantic_key": semanticKey,
                "country": userCountry,
                "interest": interestOne,
                "response": json_data.get("response", ""),
                "json_url": item["json_url"],
            }
        except requests.RequestException as e:
            print(f"Failed to fetch response from S3: {e}")
            return {
                "landmark": landmark_id,
                "semantic_key": semanticKey,
                "country": userCountry,
                "interest": interestOne,
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
@app.post("/ask-landmark/")
async def ask_landmark_question(
    landmark: str = Form(...),
    question: str = Form(None),
    userCountry: str = Form("default"),
    interestOne: str = Form(""),
    audio_file: UploadFile = File(None)
):
    """
    Handle follow-up questions by:
    1. Accepting either text question or audio file
    2. Converting audio to text if provided
    3. Using semantic matching to find the most relevant semantic key
    4. Fetching the response using that key
    5. Falling back to LLM if no static response found
    """
    try:
        # 1. Normalize landmark ID
        landmark_id = landmark.replace(" ", "_")
        
        # 2. Get the question - either from text or convert from audio
        if audio_file:
            print(f"🎤 Processing audio file: {audio_file.filename}")
            
            # Read audio file
            audio_content = await audio_file.read()
            
            # Get file extension
            file_extension = audio_file.filename.split(".")[-1] if "." in audio_file.filename else "m4a"
            
            # Convert audio to text
            question_text = await audio_processing_service.audio_to_text(audio_content, file_extension)
            print(f"🎤 Audio converted to question: '{question_text}'")
            
        elif question:
            question_text = question
            print(f"📝 Processing text question: '{question_text}'")
        else:
            raise HTTPException(status_code=400, detail="Either question or audio_file must be provided")
        
        print(f"🎯 Processing question for landmark: {landmark_id}")
        print(f"❓ Question: {question_text}")
        
        # 3. Get semantic key using FAISS-based semantic matching
        semantic_key, confidence = semantic_matching_service.get_landmark_specific_semantic_key(
            question_text, 
            landmark_id
        )
        
        # 4. If we found a semantic key, try to get static response
        if semantic_key:
            # Normalize country mapping
            country_map = {
                "UnitedStatesofAmerica": "United States",
                "USA": "United States",
                "US": "United States"
            }
            userCountry = country_map.get(userCountry, userCountry)

            # Compose key dynamically based on semanticKey
            semantic_country_key = f"{semantic_key}#{userCountry}#{interestOne}"
            print(f"🔑 Looking for semantic key: {semantic_country_key}")

            # Query the semantic_responses table
            semantic_table = dynamodb.Table("semantic_responses")
            response = semantic_table.get_item(
                Key={
                    "landmark_id": landmark_id,
                    "semantic_country_key": semantic_country_key
                }
            )

            item = response.get("Item")
            if item:
                print(f"✅ Found static response")
                
                # Fetch the actual response content from S3
                try:
                    json_response = requests.get(item["json_url"], timeout=10)
                    json_response.raise_for_status()
                    json_data = json_response.json()
                    actual_response = json_data.get("response", "")
                    print(f"📄 Fetched response from S3: {actual_response[:100]}...")
                    
                    return {
                        "landmark": landmark_id,
                        "question": question_text,
                        "answer": actual_response,
                        "semantic_key": semantic_key,
                        "confidence": float(confidence),
                        "source": "static",
                        "json_url": item.get("json_url", "")
                    }
                except requests.RequestException as e:
                    print(f"Failed to fetch response from S3: {e}")
                    return {
                        "landmark": landmark_id,
                        "question": question_text,
                        "answer": "Response content unavailable",
                        "semantic_key": semantic_key,
                        "confidence": float(confidence),
                        "source": "static",
                        "json_url": item.get("json_url", "")
                    }
            else:
                print(f"⚠️ No static response found for key: {semantic_country_key}")
        
        # 5. Fallback response (for now, just return a message)
        # TODO: Integrate with LLM service
        return {
            "landmark": landmark_id,
            "question": question_text,
            "answer": f"I don't have a specific answer for that question about {landmark_id}. This would be a good candidate for LLM generation.",
            "semantic_key": None,
            "confidence": None,
            "source": "llm_fallback"
        }
        
    except Exception as e:
        print("🔥 ERROR in /ask-landmark:", e)
        raise HTTPException(status_code=500, detail=f"Failed to process question: {str(e)}")
