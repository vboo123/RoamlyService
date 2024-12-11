from fastapi import FastAPI, HTTPException, Query
from cassandra.cluster import Cluster
from cassandra.query import SimpleStatement
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uuid

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
            age text
        )
        """
        session.execute(create_users_table_query)

        # Generate a unique user_id
        user_id = uuid.uuid4()

        # Prepare the query for inserting user data
        insert_user_query = SimpleStatement("""
            INSERT INTO users (user_id, name, email, country, interestOne, interestTwo, interestThree, age)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """)

        # Execute the insert query with user data
        session.execute(insert_user_query, (
            user_id, user.name, user.email, user.country, user.interestOne, user.interestTwo, user.interestThree, user.age
        ))

        # Return a success message with the generated user_id
        return {"message": "User registered successfully", "user_id": str(user_id)}

    except Exception as e:
        # Raise an HTTP exception in case of an error
        raise HTTPException(status_code=500, detail=f"Failed to register user: {e}")


# Define a Pydantic model for request validation
class Property(BaseModel):
    name: str  # Instead of latitude and longitude, we take name (address)
    city: str
    country: str
    mediumResponseIndiaCarsShopping: str

@app.post("/add-property/")
async def add_property(property: Property):
    """
    Dynamically adds a property to the Cassandra database, 
    creating the table if it does not exist. The latitude and longitude
    are retrieved via geocoding the property name.
    """
    try:
        # property address
        address = property.name + ", " + property.city
        # Geocode the property name to get latitude and longitude
        lat, lon = get_coordinates(address)
        if lat is None or lon is None:
            raise HTTPException(status_code=400, detail="Unable to geocode the property name")

        # Create the table if it doesn't exist
        create_table_query = """
        CREATE TABLE IF NOT EXISTS properties (
            geohash_code text,
            property_id uuid,
            name text,
            city text,
            country text,
            mediumResponseIndiaCarsShopping text,
            PRIMARY KEY (geohash_code, property_id)
        )
        """
        session.execute(create_table_query)

        # Generate geohash from latitude and longitude
        geohash_code = geohash.encode(lat, lon, precision=2)

        # Generate a unique property_id
        property_id = uuid.uuid4()

        # Prepare the query for inserting data
        insert_query = SimpleStatement("""
            INSERT INTO properties (
                geohash_code, property_id, name, city, country, mediumResponseIndiaCarsShopping
            ) 
            VALUES (%s, %s, %s, %s, %s, %s)
        """)

        # Execute the query with dynamic data
        session.execute(insert_query, (
            geohash_code, property_id, property.name, property.city, property.country, property.mediumResponseIndiaCarsShopping
        ))

        # Return a success message with the generated property_id
        return {"message": "Property added successfully", "property_id": str(property_id)}
    except Exception as e:
        # Raise an HTTP exception in case of an error
        raise HTTPException(status_code=500, detail=f"Failed to add property: {e}")

@app.get("/get-properties/")
async def get_properties(
    lat: float = Query(..., description="Latitude of the location"),
    long: float = Query(..., description="Longitude of the location")
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

        # # Query the Cassandra database for properties with matching geohash
        # select_query = """
        # SELECT * FROM properties WHERE geohash_code = %s
        # """
        # rows = session.execute(select_query, (geohash_code,))
        # Query the Cassandra database for properties with matching geohash
        select_query = """
        SELECT * FROM properties
        """
        rows = session.execute(select_query)

        properties = [
            {
                "geohash_code": row.geohash_code,
                "property_id": str(row.property_id),  # Convert UUID to string
                "name": row.name,
                "city": row.city,
                "country": row.country,
                "mediumresponseindiacarsshopping": row.mediumresponseindiacarsshopping,
            }
            for row in rows
        ]
        
        # Return the properties found
        return {"properties": properties}

    except Exception as e:
        # Raise an HTTP exception in case of an error
        raise HTTPException(status_code=500, detail=str(e))
