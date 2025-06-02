import os
import openai
import boto3
from dotenv import load_dotenv
from pinecone import Pinecone
from uuid import uuid4

# === Load environment variables ===
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# Pinecone
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index_name = os.getenv("PINECONE_INDEX_NAME", "roamly-semantic")
index = pc.Index(index_name)

# DynamoDB
dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
semantic_table = dynamodb.Table("semantic_responses")

# === Embed function ===
def get_embedding(text: str) -> list[float]:
    response = openai.Embedding.create(
        model="text-embedding-3-small",
        input=text
    )
    return response["data"][0]["embedding"]

# === Scan and upsert ===
print("📡 Scanning DynamoDB for semantic responses...")
response = semantic_table.scan()
items = response.get("Items", [])

vectors = []
for item in items:
    if "query" not in item or not item["query"].strip():
        continue

    vector_id = f"{item['landmark_id']}#{item['semantic_country_key']}"
    embedding = get_embedding(item["query"])

    metadata = {
        "landmark_id": item["landmark_id"],
        "semantic_key": item["semantic_country_key"],
        "query": item["query"]
    }

    vectors.append({
        "id": vector_id,
        "values": embedding,
        "metadata": metadata
    })

    if len(vectors) >= 100:
        index.upsert(vectors=vectors)
        print(f"🚀 Uploaded 100 vectors...")
        vectors = []

# Final batch
if vectors:
    index.upsert(vectors=vectors)
    print(f"🚀 Uploaded final {len(vectors)} vectors.")

print("✅ All semantic responses uploaded to Pinecone.")
