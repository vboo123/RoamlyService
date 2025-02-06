from fastapi import FastAPI, HTTPException, Query
from cassandra.cluster import Cluster
from cassandra.query import SimpleStatement
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from geolib import geohash
import uuid
import json

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

# Connect to the local Cassandra cluster
cluster = Cluster(['127.0.0.1'])  # Localhost
session = cluster.connect()

# Use the keyspace
session.set_keyspace('roamly_keyspace')

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
    Registers a new user by adding their information to the Users table.
    The table is created dynamically if it doesn't exist.
    """
    try:
        # Create the Users table if it doesn't exist
        create_users_table_query = """
        CREATE TABLE IF NOT EXISTS users (
            user_id uuid PRIMARY KEY,
            name text,
            email text,
            country text,
            interestOne text,
            interestTwo text,
            interestThree text,
            age text,
            language text
        )
        """
        session.execute(create_users_table_query)

        # Generate a unique user_id
        user_id = uuid.uuid4()

        # Prepare the query for inserting user data
        insert_user_query = SimpleStatement("""
            INSERT INTO users (user_id, name, email, country, interestOne, interestTwo, interestThree, age, language)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """)

        # Execute the insert query with user data
        session.execute(insert_user_query, (
            user_id, user.name, user.email, user.country, user.interestOne, user.interestTwo, user.interestThree, user.age, user.language
        ))

        # Return a success message with the generated user_id
        return {"message": "User registered successfully", "user_id": {str(user_id)}}

    except Exception as e:
        # Raise an HTTP exception in case of an error
        raise HTTPException(status_code=500, detail=f"Failed to register user: {e}")


# Define a Pydantic model for request validation
class Property(BaseModel):
    geohash: str
    landmarkName: str  # Instead of latitude and longitude, we take name (address)
    country: str
    city: str
    responses: str

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
    The geohash of the given coordinates is calculated, and properties with the same
    geohash are fetched from the database.
    """
    try:
        # Calculate the geohash based on latitude and longitude
        geohash_code = geohash.encode(lat, long, precision=2)
        print(geohash_code)

        # Query the Cassandra database for properties with matching geohash
        select_query = """
        SELECT * FROM properties WHERE geohash = %s
        """
        rows = session.execute(select_query, (f'{geohash_code}',))

        classify_age = lambda age: "young" if age < 30 else "middleage" if age <= 60 else "old"

        properties = []
        for row in rows:
            landmark_name = row.landmarkname.replace(" ", "")

            print("user country is ", userCountry)

            # Define the keys to extract from the responses JSON
            keys_to_extract = [f"{landmark_name}_{interestOne}_{interestTwo}_{interestThree}_{userCountry}_{userLanguage}_{classify_age(int(userAge))}_small", f"{landmark_name}_{interestOne}_{interestTwo}_{interestThree}_{userCountry}_{userLanguage}_{classify_age(int(userAge))}_middle", f"{landmark_name}_{interestOne}_{interestTwo}_{interestThree}_{userCountry}_{userLanguage}_{classify_age(int(userAge))}_large"]

            # Parse the JSON structure in row.responses
            responses_json = json.loads(row.responses)
            # Filter the desired keys from the JSON
            filtered_responses = {key: responses_json.get(f'{key}') for key in keys_to_extract}
            print("filtered all responses")
            # Append the property with filtered responses
            properties.append({
                "geohash": row.geohash,
                "latitude": row.latitude,
                "longitude": row.longitude,
                "landmarkName": row.landmarkname,
                "city": row.city,
                "country": row.country,
                "responses": filtered_responses,
            })

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
    If found, returns the user_id associated with the user.
    """
    try:
        # Prepare the query to find the user by name and email
        select_query = SimpleStatement("""
            SELECT user_id , name, interestone, interesttwo, interestthree, age, country, language FROM users WHERE name = %s AND email = %s ALLOW FILTERING
        """)

        # Execute the query with the provided name and email
        rows = session.execute(select_query, (name, email))

        # Fetch the first matching row (if any)
        user_row = rows.one()

        if user_row:
            return user_row
        else:
            raise HTTPException(status_code=404, detail="User not found")

    except Exception as e:
        # Handle any exceptions and return an HTTP error
        raise HTTPException(status_code=500, detail=f"Login failed: {e}")
