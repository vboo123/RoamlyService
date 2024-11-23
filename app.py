from fastapi import FastAPI, HTTPException
from cassandra.cluster import Cluster
from cassandra.query import SimpleStatement
import uuid

app = FastAPI()

# Connect to the local Cassandra cluster
cluster = Cluster(['127.0.0.1'])  # Localhost
session = cluster.connect()

# Use the keyspace
session.set_keyspace('roamly_keyspace')

@app.post("/add-property/")
async def add_property(
    geohash_code: str,
    name: str,
    city: str,
    country: str,
    information_Chinese: str,
    information_Indian: str,
    information_British: str
):
    try:
        insert_query = SimpleStatement("""
            INSERT INTO properties (geohash_code, property_id, name, city, country, 
            information_Chinese, information_Indian, information_British) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """)
        session.execute(insert_query, (
            geohash_code, uuid.uuid4(), name, city, country, 
            information_Chinese, information_Indian, information_British
        ))
        return {"message": "Property added successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/get-properties/")
async def get_properties():
    try:
        select_query = "SELECT * FROM properties"
        rows = session.execute(select_query)
        properties = [
            {
                "geohash_code": row.geohash_code,
                "property_id": str(row.property_id),
                "name": row.name,
                "city": row.city,
                "country": row.country,
                "information_Chinese": row.information_Chinese,
                "information_Indian": row.information_Indian,
                "information_British": row.information_British,
            }
            for row in rows
        ]
        return {"properties": properties}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
