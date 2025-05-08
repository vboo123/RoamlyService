from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from geolib import geohash
import uuid
import json
from cassandra.cluster import Cluster
from assembleResponse import assemble_response
import traceback
from fastapi import HTTPException
import json
import hashlib
from cassandra.query import dict_factory
from fastapi import HTTPException
import boto3
import hashlib

# Connect to Cassandra
cluster = Cluster(['127.0.0.1'])
session = cluster.connect()
session.set_keyspace('roamly_keyspace')

# FastAPI app initialization
app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Replace with specific domains in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Define a Pydantic model for user registration
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
            user_id,
            user.name,
            user.email,
            user.country,
            user.interestOne,
            user.interestTwo,
            user.interestThree,
            user.age,
            user.language
        ))

        return {"message": "User registered successfully", "user_id": user_id}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to register user: {e}")


@app.get("/get-properties/")
async def get_properties(
    lat: float = Query(..., description="Latitude of the location"),
    long: float = Query(..., description="Longitude of the location"),
    interestOne: str = Query(...),
    interestTwo: str = Query(...),
    interestThree: str = Query(...),
    userAge: str = Query(...),
    userCountry: str = Query(...),
    userLanguage: str = Query(...)
):
    try:
        geohash_code = geohash.encode(lat, long, precision=2)
        print("Query geohash:", geohash_code)

        # Fetch all items with matching geohash (scan + filter)
        scan_results = landmarks_table.scan(
            FilterExpression=Attr("geohash").eq(geohash_code)
        )

        classify_age = lambda age: "young" if age < 30 else "middleage" if age <= 60 else "old"
        age_group = classify_age(int(userAge))

        properties = []
        for item in scan_results.get("Items", []):
            landmark_name = item["landmark_id"]

            # Reconstruct the 3 hashed response keys
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

        return {"properties": properties}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DynamoDB query failed: {str(e)}")

@app.get("/login/")
async def login_user(name: str = Query(..., description="Name of the user"), email: str = Query(..., description="Email of the user")):
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


# Setup DynamoDB client
dynamodb = boto3.resource(
    'dynamodb',
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION")
)
landmarks_table = dynamodb.Table("Landmarks")

@app.get("/landmark-response")
async def get_landmark_response(
    landmark: str,
    userCountry: str = "default",
    interestOne: str = "",
    interestTwo: str = "",
    interestThree: str = ""
):
    # Normalize country
    country_map = {
        "UnitedStatesofAmerica": "United States",
        "USA": "United States",
        "US": "United States"
    }
    userCountry = country_map.get(userCountry, userCountry)

    # Hash generation logic (same as before)
    interests = sorted([interestOne, interestTwo, interestThree])
    interest_str = ",".join(interests)
    key_string = f"{landmark}|{interest_str}|English|young|medium|{userCountry}"
    response_key = hashlib.md5(key_string.encode()).hexdigest()

    print("Key string used to generate hash:", key_string)
    print("Computed response_key:", response_key)

    # Fetch from DynamoDB
    try:
        result = landmarks_table.get_item(Key={"landmark_id": landmark.replace(" ", "_")})
        item = result.get("Item")
        if not item:
            raise HTTPException(status_code=404, detail="Landmark not found")

        responses = item.get("responses", {})
        if response_key not in responses:
            raise HTTPException(status_code=404, detail="No matching response found")

        return {
            "landmark": landmark,
            "country": userCountry,
            "text": responses[response_key]["text"],
            "audio_url": responses[response_key]["audio_url"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching from DynamoDB: {str(e)}")
