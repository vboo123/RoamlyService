# RoamlyService

Backend Service that talks to database

We can use Postman or something to test these endpoints

Make sure to use pyEnv 3.11 or below (not 3.12 since some libraries dont have the support for it)

To make a post request

curl -X POST "http://192.168.1.68:8000/add-property/" \
-H "Content-Type: application/json" \
-d '{
"name": "Hollywood Sign",
"city": "Los Angeles",
"country": "USA"
}'

uvicorn main:app --host 0.0.0.0 --port 8000 --reload
