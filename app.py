from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
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

def validate_registration_data(data: UserRegistration) -> dict:
    """Validate registration data and return validation errors"""
    errors = {}
    
    # Validate name
    if not data.name or len(data.name.strip()) < 2:
        errors["name"] = "Name must be at least 2 characters long"
    
    # Validate age
    if data.age < 13 or data.age > 120:
        errors["age"] = "Age must be between 13 and 120"
    
    # Basic validation for other fields (no external dependencies)
    if not data.country or len(data.country.strip()) < 2:
        errors["country"] = "Country must be at least 2 characters long"
    
    if not data.language or len(data.language.strip()) < 2:
        errors["language"] = "Language must be at least 2 characters long"
    
    if not data.interestOne or len(data.interestOne.strip()) < 2:
        errors["interestOne"] = "Interest must be at least 2 characters long"
    
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