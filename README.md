To run server in Dev Environment, first execute:
uvicorn app:app --host 0.0.0.0 --port 8000 --reload

And then in San Luis Obispo, replace domain of API endpoint hits with:
Add user for POST Request
curl -X POST "http://192.168.1.78:8000/register-user/" \
-H "Content-Type: application/json" \
-d '{
"name": "Vboo",
"email": "vaibhavgargpgw@gmail.com",
"country": "USA",
"interestOne": "Biking",
"interestTwo": "Driving",
"interestThree": "Shopping",
"age": "5"
}'
