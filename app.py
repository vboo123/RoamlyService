from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from geolib import geohash
import uuid
import json
from cassandra.cluster import Cluster
from assembleResponse import assemble_response

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
        user_id = str(uuid.uuid4())
        session.execute("""
            INSERT INTO users (user_id, name, email, country, interestOne, interestTwo, interestThree, age, language)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (user_id, user.name, user.email, user.country, user.interestOne, user.interestTwo, user.interestThree, user.age, user.language))

        return {"message": "User registered successfully", "user_id": user_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to register user: {e}")

@app.get("/get-properties/")
async def get_properties(
    lat: float = Query(..., description="Latitude of the location"),
    long: float = Query(..., description="Longitude of the location"),
    interestOne: str = Query(..., description="interestOne of user"),
    interestTwo: str = Query(..., description="interestTwo of user"),
    interestThree: str = Query(..., description="interestThree of user"),
    userAge: str = Query(..., description="age of user"),
    userCountry: str = Query(..., description="country of user"),
    userLanguage: str = Query(..., description="language of user")
):
    try:
        # geohash_code = geohash.encode(lat, long, precision=2)
        geohash_code = "9q"
        print(geohash_code)

        rows = session.execute("SELECT * FROM properties WHERE geohash = %s", (geohash_code,))

        classify_age = lambda age: "young" if age < 30 else "middleage" if age <= 60 else "old"
        age_group = classify_age(int(userAge))

        properties = []
        for row in rows:
            landmark_name = row.landmarkname.replace(" ", "")

            keys_to_extract = [
                f"{landmark_name}_{interestOne}_{interestTwo}_{interestThree}_{userCountry}_{userLanguage}_{age_group}_small",
                f"{landmark_name}_{interestOne}_{interestTwo}_{interestThree}_{userCountry}_{userLanguage}_{age_group}_middle",
                f"{landmark_name}_{interestOne}_{interestTwo}_{interestThree}_{userCountry}_{userLanguage}_{age_group}_large"
            ]

            responses_data = json.loads(row.responses) if isinstance(row.responses, str) else row.responses
            filtered_responses = {key: responses_data.get(key) for key in keys_to_extract}

            property_data = {
                "geohash": row.geohash,
                "latitude": row.latitude,
                "longitude": row.longitude,
                "landmarkName": row.landmarkname,
                "city": row.city,
                "country": row.country,
                "responses": filtered_responses,
            }

            properties.append(property_data)

        return {"properties": properties}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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

@app.get("/landmark-response")
async def get_landmark_response(
    landmark: str,
    userCountry: str = "default",
    interestOne: str = "",
    interestTwo: str = "",
    interestThree: str = ""
):
    interests = [interestOne, interestTwo, interestThree]
    response = assemble_response(property_id=landmark, user_country=userCountry, interests=interests)
    return {
        "landmark": landmark,
        "country": userCountry,
        "response": response
    }
