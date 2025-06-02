# scripts/pinecone_init.py

import os
from dotenv import load_dotenv
from pinecone import Pinecone

# === Load .env ===
load_dotenv()
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "roamly-semantic")

# === Connect to Pinecone ===
pc = Pinecone(api_key=PINECONE_API_KEY)

# === Check if index exists ===
if PINECONE_INDEX_NAME not in pc.list_indexes().names():
    # 🧠 Get default project info (auto region)
    project = pc.whoami().project_name
    print(f"📦 Using project: {project}")

    # 🔧 Create index without specifying region/cloud
    pc.create_index(
        name=PINECONE_INDEX_NAME,
        dimension=1536,
        metric="cosine"
    )
    print(f"✅ Created index '{PINECONE_INDEX_NAME}' in project '{project}'")
else:
    print(f"✅ Index '{PINECONE_INDEX_NAME}' already exists.")
