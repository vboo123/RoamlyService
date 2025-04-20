from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from geolib import geohash
import uuid
import json
from pymongo import MongoClient
from bson.objectid import ObjectId
import os
from assembleResponse import assemble_response

# FastAPI app initialization
app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Replace "*" with specific domains in production
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
    """
    Registers a new user by adding their information to the Users collection.
    """
    try:
        # Access the users collection (will be created if it doesn't exist)
        users_collection = db["users"]
        
        # Create user document
        user_data = {
            "user_id": str(uuid.uuid4()),
            "name": user.name,
            "email": user.email,
            "country": user.country,
            "interestOne": user.interestOne,
            "interestTwo": user.interestTwo,
            "interestThree": user.interestThree,
            "age": user.age,
            "language": user.language
        }
        
        # Insert the user document
        result = users_collection.insert_one(user_data)
        
        # Return success message with user_id
        return {"message": "User registered successfully", "user_id": user_data["user_id"]}
        
    except Exception as e:
        # Raise an HTTP exception in case of an error
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
    """
    Retrieves properties near the provided latitude and longitude based on geohash.
    """
    try:
        # Calculate the geohash based on latitude and longitude
        geohash_code = geohash.encode(lat, long, precision=2)
        print(geohash_code)
        
        # Access the properties collection
        properties_collection = db["properties"]
        
        # Query MongoDB for properties with matching geohash
        cursor = properties_collection.find({"geohash": geohash_code})
        
        classify_age = lambda age: "young" if age < 30 else "middleage" if age <= 60 else "old"
        
        properties = []
        for document in cursor:
            landmark_name = document["landmarkName"].replace(" ", "")
            
            print("user country is ", userCountry)
            
            # Define the keys to extract from the responses JSON
            keys_to_extract = [
                f"{landmark_name}_{interestOne}_{interestTwo}_{interestThree}_{userCountry}_{userLanguage}_{classify_age(int(userAge))}_small", 
                f"{landmark_name}_{interestOne}_{interestTwo}_{interestThree}_{userCountry}_{userLanguage}_{classify_age(int(userAge))}_middle", 
                f"{landmark_name}_{interestOne}_{interestTwo}_{interestThree}_{userCountry}_{userLanguage}_{classify_age(int(userAge))}_large"
            ]
            
            # Parse the responses
            responses_data = document.get("responses", {})
            if isinstance(responses_data, str):
                responses_data = json.loads(responses_data)
                
            # Filter the desired keys from the responses
            filtered_responses = {key: responses_data.get(key) for key in keys_to_extract}
            print("filtered all responses")
            
            # Append the property with filtered responses
            property_data = {
                "geohash": document.get("geohash"),
                "latitude": document.get("latitude"),
                "longitude": document.get("longitude"),
                "landmarkName": document.get("landmarkName"),
                "city": document.get("city"),
                "country": document.get("country"),
                "responses": filtered_responses,
            }
            
            # Remove ObjectId to make it JSON serializable
            if "_id" in property_data:
                property_data["_id"] = str(property_data["_id"])
                
            properties.append(property_data)
            
            print("reached here")
        
        # Return the properties found
        return {"properties": properties}
        
    except Exception as e:
        # Raise an HTTP exception in case of an error
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/login/")
async def login_user(name: str = Query(..., description="Name of the user"), email: str = Query(..., description="Email of the user")):
    """
    Authenticates a user by checking if their name and email exist in the database.
    If found, returns the user information.
    """
    try:
        # Access the users collection
        users_collection = db["users"]
        
        # Find the user by name and email
        user = users_collection.find_one({"name": name, "email": email})
        
        if user:
            # Convert ObjectId to string to make it JSON serializable
            user["_id"] = str(user["_id"])
            return user
        else:
            raise HTTPException(status_code=404, detail="User not found")
            
    except Exception as e:
        # Handle any exceptions and return an HTTP error
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

# Data migration function (optional)
def migrate_data_from_cassandra():
    """
    Optional function to migrate existing data from Cassandra to MongoDB.
    You would need to run this separately with both databases connected.
    """
    try:
        from cassandra.cluster import Cluster
        
        # Connect to Cassandra
        cassandra_cluster = Cluster(['127.0.0.1'])
        cassandra_session = cassandra_cluster.connect('roamly_keyspace')
        
        # Migrate users
        users_rows = cassandra_session.execute("SELECT * FROM users")
        users_collection = db["users"]
        
        for user_row in users_rows:
            user_doc = {
                "user_id": str(user_row.user_id),
                "name": user_row.name,
                "email": user_row.email,
                "country": user_row.country,
                "interestOne": user_row.intereestone,
                "interestTwo": user_row.interesttwo,
                "interestThree": user_row.interestthree,
                "age": user_row.age,
                "language": user_row.language
            }
            users_collection.insert_one(user_doc)
            
        # Migrate properties
        properties_rows = cassandra_session.execute("SELECT * FROM properties")
        properties_collection = db["properties"]
        
        for property_row in properties_rows:
            property_doc = {
                "geohash": property_row.geohash,
                "latitude": property_row.latitude,
                "longitude": property_row.longitude,
                "landmarkName": property_row.landmarkname,
                "city": property_row.city,
                "country": property_row.country,
                "responses": json.loads(property_row.responses) if isinstance(property_row.responses, str) else property_row.responses
            }
            properties_collection.insert_one(property_doc)
            
        print("Data migration completed successfully")
        
    except Exception as e:
        print(f"Migration failed: {e}")
        
# If you need to run the migration, uncomment the line below
# migrate_data_from_cassandra()