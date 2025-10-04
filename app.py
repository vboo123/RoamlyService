from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from typing import Optional
import boto3
import uuid
import json
import os
import traceback
from dotenv import load_dotenv
import decimal
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from datetime import datetime, timedelta
import jwt
from jwt import PyJWTError
import hashlib
from s3_operations import create_customer_bucket, deep_update, get_persona_from_s3, save_persona_to_s3, create_default_traveler_persona

# === Load environment variables ===
load_dotenv()

# === Setup DynamoDB ===
dynamodb = boto3.resource(
    'dynamodb',
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name="us-east-2"
)
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
    username: str
    password: str
    persona: str  # S3 link to persona

    class Config:
        json_schema_extra = {
            "example": {
                "username": "johndoe",
                "password": "securepassword123",
                "persona": "https://s3.amazonaws.com/bucket/personas/johndoe.json"
            }
        }

class UserLogin(BaseModel):
    username: str
    password: str

    class Config:
        json_schema_extra = {
            "example": {
                "username": "johndoe",
                "password": "securepassword123"
            }
        }

class UpdateTravelerPersonaRequest(BaseModel):
    customerId: str
    username: str
    target: str  # "traveler", "trip", or "tour"
    targetId: Optional[str] = None  # Required for trip and tour targets
    updates: dict

    class Config:
        json_schema_extra = {
            "example": {
                "customerId": "user_123",
                "username": "alexjones",
                "target": "traveler",
                "targetId": None,
                "updates": {
                    "travel_persona": {
                        "preferences": {
                            "vibe": "Energetic",
                            "focus": "Beach & Nightlife"
                        }
                    }
                }
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

def hash_password(password: str) -> str:
    """Hash password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, hashed_password: str) -> bool:
    """Verify password against hash"""
    return hash_password(password) == hashed_password
def validate_registration_data(data: UserRegistration) -> dict:
    """Validate registration data and return validation errors"""
    errors = {}
    
    # Validate username
    if not data.username or len(data.username.strip()) < 3:
        errors["username"] = "Username must be at least 3 characters long"
    
    # Validate password
    if not data.password or len(data.password) < 6:
        errors["password"] = "Password must be at least 6 characters long"
    
    # Validate persona (basic URL validation)
    if not data.persona or not data.persona.startswith(("http://", "https://")):
        errors["persona"] = "Persona must be a valid URL"
    
    return errors

def validate_login_data(data: UserLogin) -> dict:
    """Validate login data and return validation errors"""
    errors = {}
    
    # Validate username
    if not data.username or len(data.username.strip()) < 3:
        errors["username"] = "Username must be at least 3 characters long"
    
    # Validate password
    if not data.password or len(data.password) < 6:
        errors["password"] = "Password must be at least 6 characters long"
    
    return errors
JWT_SECRET = os.getenv("JWT_SECRET", "supersecretkey")
JWT_ALGORITHM = "HS256"
JWT_EXP_DELTA_SECONDS = 60 * 60 * 24 * 7  # 7 days

def create_jwt_token(customer_id: str, username: str):
    payload = {
        "customer_id": customer_id,
        "username": username,
        
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
    if not payload or "customer_id" not in payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    # Optionally, check if user still exists in DB
    user = users_table.get_item(Key={"customer_id": payload["customer_id"]}).get("Item")
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

# === API Endpoints ===

@app.post("/update-traveler-persona/")
@limiter.limit("10/minute")  # Rate limit: 10 requests per minute per IP
async def update_traveler_persona(request_data: UpdateTravelerPersonaRequest, request: Request):
    """Update traveler persona data in S3"""
    try:
        print(f"🔄 Persona update attempt from IP: {get_remote_address(request)}")
        print(f"📝 Update data: {request_data.dict()}")
        
        # Validate target and targetId
        if request_data.target not in ["traveler", "trip", "tour"]:
            raise HTTPException(
                status_code=422,
                detail="Invalid target. Must be 'traveler', 'trip', or 'tour'"
            )
        
        if request_data.target in ["trip", "tour"] and (not request_data.targetId or request_data.targetId is None):
            raise HTTPException(
                status_code=422,
                detail=f"targetId is required for target '{request_data.target}'"
            )
        
        print(f"🔧 About to call create_customer_bucket with: {request_data.customerId}, {request_data.username}")
        
        # Create or ensure bucket exists
        bucket_result = create_customer_bucket(request_data.customerId, request_data.username)
        print(f"🔧 Bucket result: {bucket_result}")
        
        if bucket_result["status"] != "success":
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create/access bucket: {bucket_result['message']}"
            )
        
        bucket_name = bucket_result["bucket_name"]
        
        # Determine the S3 key based on target
        if request_data.target == "traveler":
            key = "travelerPersona.json"
        elif request_data.target == "trip":
            key = f"trips/{request_data.targetId}_trip.json"
        elif request_data.target == "tour":
            key = f"tours/{request_data.targetId}_tour.json"
        
        # Get existing persona data
        existing_data = get_persona_from_s3(bucket_name, key)
        
        # If no existing data and target is traveler, create default persona
        if not existing_data and request_data.target == "traveler":
            existing_data = create_default_traveler_persona(request_data.customerId, request_data.username)
            print(f"📄 Created default traveler persona for {request_data.customerId}")
        
        # If no existing data for trip/tour, create empty structure
        elif not existing_data and request_data.target in ["trip", "tour"]:
            existing_data = {
                "customerId": request_data.customerId,
                "lastUpdated": datetime.utcnow().isoformat() + "Z"
            }
            if request_data.target == "trip":
                existing_data.update({
                    "trip_id": request_data.targetId,
                    "location": {"city": "", "country": ""},
                    "dates": {"start": "", "end": ""},
                    "preferences": {},
                    "itinerary_link": "",
                    "custom_tours": {}
                })
            elif request_data.target == "tour":
                existing_data.update({
                    "tour_id": request_data.targetId,
                    "trip_id": "",
                    "tour_name": "",
                    "date": "",
                    "duration": "",
                    "preferences": {},
                    "notes": ""
                })
            print(f"📄 Created empty {request_data.target} persona for {request_data.targetId}")
        
        # Perform deep update
        updated_data = deep_update(existing_data, request_data.updates)
        
        # Update lastUpdated timestamp
        updated_data["lastUpdated"] = datetime.utcnow().isoformat() + "Z"
        
        # Save updated data to S3
        save_success = save_persona_to_s3(bucket_name, key, updated_data)
        
        if not save_success:
            raise HTTPException(
                status_code=500,
                detail="Failed to save updated persona to S3"
            )
        
        print(f"✅ Successfully updated {request_data.target} persona: {key}")
        
        return {
            "status": "success",
            "message": f"Successfully updated {request_data.target} persona",
            "updatedKey": key,
            "bucketName": bucket_name
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Persona update error: {e}")
        print(f"🔍 Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Persona update failed: {str(e)}")

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
        
        # Check if username already exists
        response = users_table.scan(
            FilterExpression="username = :username",
            ExpressionAttributeValues={":username": user_data.username.lower()}
        
        )        
        if response.get("Items"):
            print(f"❌ Username already exists: {user_data.username}")
            raise HTTPException(
                status_code=409, 
                detail="Username already exists"
            )
        
        # Generate customer_id (primary key)
        customer_id = str(uuid.uuid4())
        
        # Hash the password
        hashed_password = hash_password(user_data.password)
        
        # Create user item
        user_item = {
            "customer_id": customer_id,  # Primary key
            "username": user_data.username.lower().strip(),
            "password": hashed_password,  # Store hashed password
            "persona": user_data.persona.strip(),
            "created_at": datetime.utcnow().isoformat(),
            "last_login": datetime.utcnow().isoformat()
        }        
        # Store in DynamoDB
        users_table.put_item(Item=user_item)
        
        # Create initial traveler persona
        try:
            persona_update_request = UpdateTravelerPersonaRequest(
                customerId=customer_id,
                username=user_data.username,
                target="traveler",
                targetId=None,
                updates={}  # Empty updates will create default persona
            )
            
            # Call the update persona endpoint internally
            persona_result = await update_traveler_persona(persona_update_request, request)
            print(f"✅ Created initial traveler persona: {persona_result['updatedKey']}")
            
        except Exception as persona_error:
            print(f"⚠️ Warning: Failed to create initial persona: {persona_error}")
            # Don't fail registration if persona creation fails
            # The persona can be created later
        
        print(f"✅ User registered successfully: {user_data.username}")
        
        return {
            "status": "success",
            "message": "User registered successfully",
            "customer_id": customer_id,
            "user": convert_dynamodb_types({
                "customer_id": customer_id,
                "username": user_data.username,
                "persona": user_data.persona,
                "created_at": user_item["created_at"]
            })
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Registration error: {e}")
        print(f"🔍 Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Registration failed")

@app.post("/login/")
@limiter.limit("5/minute")
async def login_user(login_data: UserLogin, request: Request):
    """Login user with username and password"""
    try:
        print(f"🔐 Login attempt from IP: {get_remote_address(request)}")
        print(f"📝 Login data: {login_data.dict()}")
        
        # Validate login data
        validation_errors = validate_login_data(login_data)
        if validation_errors:
            print(f"❌ Validation errors: {validation_errors}")
            raise HTTPException(
                status_code=422, 
                detail={
                    "message": "Validation failed",
                    "errors": validation_errors
                }
            )
        
        # Find user by username
        response = users_table.scan(
            FilterExpression="username = :username",
            ExpressionAttributeValues={":username": login_data.username.lower()}
        )
        
        users = response.get("Items", [])
        if not users:
            print(f"❌ User not found: {login_data.username}")
            raise HTTPException(status_code=404, detail="User not found")
        
        user = users[0]  # Get first match
        
        # Verify password
        if not verify_password(login_data.password, user["password"]):
            print(f"❌ Invalid password for user: {login_data.username}")
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Update last login
        users_table.update_item(
            Key={"customer_id": user["customer_id"]},
            UpdateExpression="SET last_login = :last_login",
            ExpressionAttributeValues={":last_login": datetime.utcnow().isoformat()}
        )
        
        # Create JWT token
        token = create_jwt_token(user["customer_id"], user["username"])
        
        print(f"✅ User logged in successfully: {login_data.username}")
        
        return {
            "status": "success",
            "message": "Login successful",
            "token": token,
            "user": convert_dynamodb_types({
                "customer_id": user["customer_id"],
                "username": user["username"],
                "persona": user["persona"],
                "last_login": user["last_login"]
            })
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Login error: {e}")
        print(f"🔍 Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Login failed")

@app.get("/profile/")
async def get_user_profile(request: Request):
    """Get current user profile (requires authentication)"""
    try:
        user = get_current_user(request)
        
        return {
            "status": "success",
            "user": convert_dynamodb_types({
                "customer_id": user["customer_id"],
                "username": user["username"],
                "persona": user["persona"],
                "created_at": user["created_at"],
                "last_login": user["last_login"]
            })
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Profile error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get profile")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
