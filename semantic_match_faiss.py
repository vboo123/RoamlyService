from sentence_transformers import SentenceTransformer, util
import faiss
import numpy as np

# === Load embedding model (FREE + offline) ===
model = SentenceTransformer('all-MiniLM-L6-v2')
dimension = 384  # This model outputs 384-dimensional vectors

# === Sample Data ===
semantic_data = [
    {
        "key": "hollywood-sign.height.general",
        "text": "It stands at 45 feet tall. Iconic and easy to spot from afar.",
        "query": "how tall is it?"
    },
    {
        "key": "hollywood-sign.origin.general",
        "text": "It was originally built in 1923 as a real estate ad.",
        "query": "when was it made?"
    },
    {
        "key": "hollywood-sign.media.references",
        "text": "It’s been featured in countless movies, music videos, and TV shows.",
        "query": "was it in any movies?"
    }
]

# === Build FAISS Index ===
index = faiss.IndexFlatL2(dimension)
vectors = []
metadata = []

print("Generating embeddings and building FAISS index...")
for item in semantic_data:
    emb = model.encode(item["query"])
    vectors.append(emb)
    metadata.append(item)

index.add(np.array(vectors).astype('float32'))
print("Index built with", len(metadata), "entries.")

# === Query Interface ===
def query_faiss(question):
    q_emb = model.encode(question).reshape(1, -1).astype('float32')
    D, I = index.search(q_emb, k=1)
    match = metadata[I[0][0]]
    score = D[0][0]
    return match, score

# === Example Run ===
if __name__ == '__main__':
    user_question = input("Ask a follow-up question: ")
    result, score = query_faiss(user_question)
    if score < 0.7:  # L2 distance threshold (tune this based on tests)
        print("\n✅ Match Found!")
        print("Semantic Key:", result["key"])
        print("Response:", result["text"])
        print("Score (L2 Distance):", score)
    else:
        print("\n⚠️ No confident match found. Consider calling LLM.")
        print("Score (L2 Distance):", score)
