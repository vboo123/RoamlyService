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
import hashlib

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
