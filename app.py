from fastapi import FastAPI, HTTPException, Query, File, UploadFile, Form, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
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
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import time
from datetime import datetime, timedelta
import jwt
from jwt import PyJWTError
from geolib import geohash

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

# === Setup S3 ===
s3_client = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION", "us-east-2")
)
S3_BUCKET = os.getenv("S3_BUCKET_NAME")

# === Setup Rate Limiting ===
limiter = Limiter(key_func=get_remote_address)
app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Pydantic Models for Validation ===
class UserRegistration(BaseModel):
    name: str
    email: EmailStr
    country: str
    language: str
    age: int
    interestOne: str

    class Config:
        json_schema_extra = {
            "example": {
                "name": "John Doe",
                "email": "john@example.com",
                "country": "United States",
                "language": "English",
                "age": 25,
                "interestOne": "Nature"
            }
        }

# === Utility Functions ===
def convert_dynamodb_types(obj):
    if isinstance(obj, list):
        return [convert_dynamodb_types(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: convert_dynamodb_types(v) for k, v in obj.items()}
    elif isinstance(obj, decimal.Decimal):
        return float(obj) if "." in str(obj) else int(obj)
    return obj

def get_options_from_s3(file_key: str) -> dict:
    """Fetch options (countries, languages, interests) from S3"""
    try:
        response = s3_client.get_object(Bucket=S3_BUCKET, Key=file_key)
        content = response['Body'].read().decode('utf-8')
        return json.loads(content)
    except Exception as e:
        print(f"❌ Error fetching {file_key} from S3: {e}")
        # Return default options if S3 fetch fails
        if file_key == "config/countries.json":
            return {"countries": ["United States", "India", "Canada", "Mexico"]}
        elif file_key == "config/languages.json":
            return {"languages": ["English", "Spanish", "Hindi"]}
        elif file_key == "config/interests.json":
            return {"interests": ["Nature", "History", "Food", "Museums", "Adventure", "Beaches", "Architecture", "Fitness", "Travel", "Technology"]}
        return {"error": f"Failed to fetch {file_key}"}

def validate_registration_data(data: UserRegistration) -> dict:
    """Validate registration data and return validation errors"""
    errors = {}
    
    # Validate name
    if not data.name or len(data.name.strip()) < 2:
        errors["name"] = "Name must be at least 2 characters long"
    
    # Validate age
    if data.age < 13 or data.age > 120:
        errors["age"] = "Age must be between 13 and 120"
    
    # Validate country (fetch from S3 and check)
    try:
        countries_data = get_options_from_s3("config/countries.json")
        valid_countries = countries_data.get("countries", [])
        if data.country not in valid_countries:
            errors["country"] = f"Invalid country. Must be one of: {', '.join(valid_countries)}"
    except Exception as e:
        print(f"⚠️ Could not validate country: {e}")
    
    # Validate language (fetch from S3 and check)
    try:
        languages_data = get_options_from_s3("config/languages.json")
        valid_languages = languages_data.get("languages", [])
        if data.language not in valid_languages:
            errors["language"] = f"Invalid language. Must be one of: {', '.join(valid_languages)}"
    except Exception as e:
        print(f"⚠️ Could not validate language: {e}")
    
    # Validate interest (fetch from S3 and check)
    try:
        interests_data = get_options_from_s3("config/interests.json")
        valid_interests = interests_data.get("interests", [])
        if data.interestOne not in valid_interests:
            errors["interestOne"] = f"Invalid interest. Must be one of: {', '.join(valid_interests)}"
    except Exception as e:
        print(f"⚠️ Could not validate interest: {e}")
    
    return errors

JWT_SECRET = os.getenv("JWT_SECRET", "supersecretkey")
JWT_ALGORITHM = "HS256"
JWT_EXP_DELTA_SECONDS = 60 * 60 * 24 * 7  # 7 days

def create_jwt_token(user_email: str):
    payload = {
        "email": user_email,
        "exp": datetime.utcnow() + timedelta(seconds=JWT_EXP_DELTA_SECONDS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_jwt_token(token: str):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except PyJWTError:
        return None

def get_current_user(request: Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = auth_header.split(" ", 1)[1]
    payload = decode_jwt_token(token)
    if not payload or "email" not in payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    # Optionally, check if user still exists in DB
    user = users_table.get_item(Key={"email": payload["email"]}).get("Item")
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

# === API Endpoints ===

@app.get("/countries/")
async def get_countries():
    """Get list of available countries from S3"""
    try:
        countries_data = get_options_from_s3("config/countries.json")
        return {
            "status": "success",
            "data": countries_data.get("countries", []),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        print(f"❌ Error in get_countries: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch countries")

@app.get("/languages/")
async def get_languages():
    """Get list of available languages from S3"""
    try:
        languages_data = get_options_from_s3("config/languages.json")
        return {
            "status": "success",
            "data": languages_data.get("languages", []),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        print(f"❌ Error in get_languages: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch languages")

@app.get("/interests/")
async def get_interests():
    """Get list of available interests from S3"""
    try:
        interests_data = get_options_from_s3("config/interests.json")
        return {
            "status": "success",
            "data": interests_data.get("interests", []),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        print(f"❌ Error in get_interests: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch interests")

@app.post("/register-user/")
@limiter.limit("5/minute")  # Rate limit: 5 requests per minute per IP
async def register_user(user_data: UserRegistration, request: Request):
    """Register a new user with validation and rate limiting"""
    try:
        print(f"🔐 Registration attempt from IP: {get_remote_address(request)}")
        print(f"📝 User data: {user_data.dict()}")
        
        # Validate registration data
        validation_errors = validate_registration_data(user_data)
        if validation_errors:
            print(f"❌ Validation errors: {validation_errors}")
            raise HTTPException(
                status_code=422, 
                detail={
                    "message": "Validation failed",
                    "errors": validation_errors
                }
            )
        
        # Check if user already exists
        existing_user = users_table.get_item(
            Key={"email": user_data.email.lower()}
        )
        
        if existing_user.get("Item"):
            print(f"❌ User already exists: {user_data.email}")
            raise HTTPException(
                status_code=409, 
                detail="User with this email already exists"
            )
        
        # Generate user ID
        user_id = str(uuid.uuid4())
        
        # Create user item
        user_item = {
            "user_id": user_id,
            "name": user_data.name.strip(),
            "email": user_data.email.lower().strip(),
            "country": user_data.country,
            "language": user_data.language,
            "age": user_data.age,
            "interestOne": user_data.interestOne,
            "created_at": datetime.utcnow().isoformat(),
            "last_login": datetime.utcnow().isoformat()
        }
        
        # Store in DynamoDB
        users_table.put_item(Item=user_item)
        
        print(f"✅ User registered successfully: {user_data.email}")
        
        return {
            "status": "success",
            "message": "User registered successfully",
            "user_id": user_id,
            "user": convert_dynamodb_types(user_item)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Registration error: {e}")
        print(f"🔍 Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Registration failed")

@app.post("/login/")
@limiter.limit("5/minute")
async def login_user(request: Request, name: str = Query(...), email: str = Query(...)):
    try:
        result = users_table.get_item(Key={"email": email})
        user = result.get("Item")
        if not user or user.get("name") != name:
            raise HTTPException(status_code=404, detail="User not found")
        token = create_jwt_token(email)
        return {"user": convert_dynamodb_types(user), "token": token}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Login failed: {e}")

@app.get("/get-properties/")
@limiter.limit("5/minute")
async def get_properties(
    lat: float, long: float,
    interestOne: str,
    userAge: str, userCountry: str, userLanguage: str,
    request: Request,
    user=Depends(get_current_user)
):
    try:
        geohash_code = geohash.encode(lat, long, 6)
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
@limiter.limit("5/minute")
async def get_landmark_response(
    landmark: str,
    request: Request,
    user=Depends(get_current_user),
    interest: str = Query("Nature", alias="interest[]"),
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
@limiter.limit("5/minute")
async def ask_landmark_endpoint(
    request: Request,
    landmark: str = Form(...),
    userId: str = Form(...),
    user=Depends(get_current_user),
    question: str = Form(None),
    userCountry: str = Form("United States"),
    interestOne: str = Form("Nature"),
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
