from fastapi import FastAPI, HTTPException
from cassandra.cluster import Cluster
from cassandra.query import SimpleStatement
from geolib import geohash
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import uuid

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



# Set some sample Geohashing
latitude = 34.13425221700465 
longitude = -118.32189112901952
# Encode the coordinates into a geohash
geohash_code = geohash.encode(latitude, longitude, precision=12)
# Use the keyspace
session.set_keyspace('roamly_keyspace')


# Define a Pydantic model for request validation
class Property(BaseModel):
    latitude: float
    longitude: float
    name: str
    city: str
    country: str

@app.post("/add-property/")
async def add_property(property: Property):
    """
    Dynamically adds a property to the Cassandra database, 
    creating the table if it does not exist.
    """
    try:
        # Create the table if it doesn't exist
        create_table_query = """
        CREATE TABLE IF NOT EXISTS properties (
            geohash_code text,
            property_id uuid,
            name text,
            city text,
            country text,
            PRIMARY KEY (geohash_code, property_id)
        )
        """
        session.execute(create_table_query)

        # Generate geohash from latitude and longitude
        geohash_code = geohash.encode(property.latitude, property.longitude, precision=12)

        # Generate a unique property_id
        property_id = uuid.uuid4()

        # Prepare the query for inserting data
        insert_query = SimpleStatement("""
            INSERT INTO properties (
                geohash_code, property_id, name, city, country
            ) 
            VALUES (%s, %s, %s, %s, %s)
        """)

        # Execute the query with dynamic data
        session.execute(insert_query, (
            geohash_code, property_id, property.name, property.city, property.country
        ))

        # Return a success message with the generated property_id
        return {"message": "Property added successfully", "property_id": str(property_id)}
    except Exception as e:
        # Raise an HTTP exception in case of an error
        raise HTTPException(status_code=500, detail=f"Failed to add property: {e}")

@app.get("/get-properties/")
async def get_properties():
    try:
        select_query = "SELECT * FROM properties"
        rows = session.execute(select_query)
        properties = [
            {
                "geohash_code": row.geohash_code,
                "property_id": str(row.property_id),  # Convert UUID to string
                "name": row.name,
                "city": row.city,
                "country": row.country,
            }
            for row in rows
        ]
        return {"properties": properties}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

