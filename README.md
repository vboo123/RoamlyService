# RoamlyService

Backend Service that talks to database

We can use Postman or something to test these endpoints

Make sure to use pyEnv 3.11 or below (not 3.12 since some libraries dont have the support for it)

To make a post request

curl -X POST "http://127.0.0.1:8000/add-property/" \
-H "Content-Type: application/json" \
-d '{
"latitude": 34.13425221700465,
"longitude": -118.32189112901952,
"name": "Hollywood Sign",
"city": "Los Angeles",
"country": "USA"
}'

uvicorn main:app --host 0.0.0.0 --port 8000 --reload
