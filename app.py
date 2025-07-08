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
import requests
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

def get_landmark_specific_semantic_key(question: str, landmark_id: str, threshold: float = 0.7):
    """
    Get the best semantic key for a question, using existing metadata structure.
    """
    try:
        # 1. Load landmarks metadata to get landmark type
        with open("scripts/landmarks.json", "r") as f:
            landmarks_data = json.load(f)
        
        # 2. Load semantic config
        with open("scripts/semantic_config.json", "r") as f:
            semantic_config = json.load(f)
        
        # 3. Find landmark and get its type - FIXED: Better name matching
        landmark_type = None
        normalized_landmark_id = landmark_id.lower().replace("_", " ")
        
        for landmark in landmarks_data:
            landmark_name_lower = landmark["name"].lower()
            if landmark_name_lower == normalized_landmark_id:
                landmark_type = landmark["type"]
                break
        
        if not landmark_type:
            print(f"⚠️ Landmark '{landmark_id}' not found in landmarks.json")
            print(f"🔍 Looking for: '{normalized_landmark_id}'")
            print(f"📋 Available landmarks: {[l['name'] for l in landmarks_data]}")
            return None, None
        
        # 4. Get available semantic keys for this landmark type
        available_keys = list(semantic_config.get(landmark_type, {}).keys())
        print(f"🔍 Landmark: {landmark_id} -> Type: {landmark_type}")
        print(f"📋 Available keys: {available_keys}")
        
        # 5. Simple keyword matching for now (we'll enhance this later)
        question_lower = question.lower()
        
        # Define keyword mappings
        keyword_mappings = {
            "origin.general": ["how did it come to be", "when was it built", "how was it created", "what's the history", "origin story"],
            "origin.name": ["name meaning", "why called", "naming", "name origin", "what does the name mean"],
            "architecture.style": ["what style is it", "architecture", "design", "how does it look", "architectural features", "architectural style"],
            "height.general": ["how tall", "height", "how high", "tallness", "elevation"],
            "experience.vibe": ["what's the vibe", "atmosphere", "feel", "mood", "what's it like"],
            "access.cost": ["how much", "cost", "price", "ticket", "entry fee"],
            "access.hours": ["hours", "opening times", "when open", "schedule"],
            "culture.symbolism": ["symbols", "meaning", "symbolism", "cultural significance"],
            "myths.legends": ["myths", "legends", "stories", "folklore", "tales"],
            "access.crowds": ["crowds", "busy", "crowded", "people", "visitors"]
        }
        
        # 6. Find matching semantic key
        best_match = None
        best_score = 0
        
        for semantic_key in available_keys:
            if semantic_key in keyword_mappings:
                keywords = keyword_mappings[semantic_key]
                for keyword in keywords:
                    if keyword in question_lower:
                        # Simple scoring: longer keyword matches get higher scores
                        score = len(keyword) / len(question_lower)
                        if score > best_score:
                            best_score = score
                            best_match = semantic_key
        
        if best_match and best_score > 0.1:  # Threshold for keyword matching
            print(f"✅ Keyword match: {best_match} (score: {best_score:.3f})")
            return best_match, best_score
        else:
            print(f"❌ No keyword match found")
            return None, None
            
    except Exception as e:
        print(f"🔥 ERROR in semantic matching: {e}")
        return None, None

@app.post("/ask-landmark/")
async def ask_landmark_question(request: LandmarkQuestion):
    """
    Handle follow-up questions by:
    1. Using semantic matching to find the most relevant semantic key
    2. Fetching the response using that key
    3. Falling back to LLM if no static response found
    """
    try:
        # 1. Normalize landmark ID
        landmark_id = request.landmark.replace(" ", "_")
        
        print(f"🎯 Processing question for landmark: {landmark_id}")
        print(f"❓ Question: {request.question}")
        
        # 2. Get semantic key using existing metadata structure
        semantic_key, confidence = get_landmark_specific_semantic_key(
            request.question, 
            landmark_id
        )
        
        # 3. If we found a semantic key, try to get static response
        if semantic_key:
            # Normalize country mapping
            country_map = {
                "UnitedStatesofAmerica": "United States",
                "USA": "United States",
                "US": "United States"
            }
            userCountry = country_map.get(request.userCountry, request.userCountry)

            # Compose key dynamically based on semanticKey
            semantic_country_key = f"{semantic_key}#{userCountry}#{request.interestOne}"
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
                return {
                    "landmark": landmark_id,
                    "question": request.question,
                    "answer": item.get("response", ""),
                    "semantic_key": semantic_key,
                    "confidence": float(confidence),
                    "source": "static",
                    "json_url": item.get("json_url", "")
                }
            else:
                print(f"⚠️ No static response found for key: {semantic_country_key}")
        
        # 4. Fallback response (for now, just return a message)
        # TODO: Integrate with LLM service
        return {
            "landmark": landmark_id,
            "question": request.question,
            "answer": f"I don't have a specific answer for that question about {landmark_id}. This would be a good candidate for LLM generation.",
            "semantic_key": None,
            "confidence": None,
            "source": "llm_fallback"
        }
        
    except Exception as e:
        print("🔥 ERROR in /ask-landmark:", e)
        raise HTTPException(status_code=500, detail=f"Failed to process question: {str(e)}")
