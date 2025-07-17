import json
import os
import boto3
import numpy as np
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Optional, Tuple
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class S3VectorSearchService:
    """
    Amazon S3 Vector Search service for semantic matching.
    Replaces FAISS with S3 Vector Search for better scalability and cost efficiency.
    """
    
    def __init__(self):
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        self.dimension = 384
        self.s3_client = boto3.client(
            "s3",
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            region_name=os.getenv("AWS_REGION", "us-east-2")
        )
        self.bucket_name = os.getenv("S3_BUCKET_NAME")
        self.vector_bucket_name = f"{self.bucket_name}-vectors"  # Separate bucket for vectors
        
        # Initialize semantic examples (same as your current FAISS service)
        self.semantic_examples = self._get_semantic_examples()
        
        # Initialize the vector index in S3
        self._initialize_vector_index()
    
    def _get_semantic_examples(self) -> Dict[str, List[str]]:
        """Get semantic key examples with multiple variations."""
        return {
            "origin.general": [
                "how did it come to be",
                "when was it built", 
                "how was it created",
                "what's the history",
                "origin story",
                "when was this built",
                "how did this get here",
                "what's the story behind this"
            ],
            "origin.name": [
                "name meaning",
                "why called",
                "naming",
                "name origin", 
                "what does the name mean",
                "why is it called",
                "how did it get its name",
                "what's the meaning of the name"
            ],
            "architecture.style": [
                "what style is it",
                "architecture",
                "design",
                "how does it look",
                "architectural features",
                "architectural style",
                "what kind of building is this",
                "how was this designed"
            ],
            "height.general": [
                "how tall",
                "height",
                "how high",
                "tallness",
                "elevation",
                "what's the height",
                "how tall is this",
                "what's the elevation"
            ],
            "experience.vibe": [
                "what's the vibe",
                "atmosphere",
                "feel",
                "mood",
                "what's it like",
                "how does it feel",
                "what's the atmosphere like",
                "what's the mood here"
            ],
            "access.cost": [
                "how much",
                "cost",
                "price",
                "ticket",
                "entry fee",
                "how much does it cost",
                "what's the price",
                "how much to enter"
            ],
            "access.hours": [
                "hours",
                "opening times",
                "when open",
                "schedule",
                "what time does it open",
                "when is it open",
                "what are the hours",
                "opening hours"
            ],
            "culture.symbolism": [
                "symbols",
                "meaning",
                "symbolism",
                "cultural significance",
                "what does it represent",
                "what's the meaning",
                "cultural meaning",
                "what does this symbolize"
            ],
            "myths.legends": [
                "myths",
                "legends",
                "stories",
                "folklore",
                "tales",
                "urban legends",
                "mythical stories",
                "legendary tales"
            ],
            "access.crowds": [
                "crowds",
                "busy",
                "crowded",
                "people",
                "visitors",
                "how many people",
                "how crowded",
                "how busy",
                "how many visitors",
                "how many people visit",
                "how many people come",
                "how many people tend to come",
                "how many people like to visit"
            ]
        }
    
    def _initialize_vector_index(self):
        """Initialize the vector index in S3."""
        print("🔧 Initializing S3 Vector Search index...")
        
        try:
            # Create vector index configuration
            index_config = {
                "dimensions": self.dimension,
                "metric": "cosine",  # Using cosine similarity
                "index_type": "hnsw",  # Hierarchical Navigable Small World
                "parameters": {
                    "m": 16,  # Number of connections per layer
                    "ef_construction": 200,  # Search depth during construction
                    "ef_search": 100  # Search depth during query
                }
            }
            
            # Store index configuration in S3
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key="vector_index/config.json",
                Body=json.dumps(index_config),
                ContentType="application/json"
            )
            
            # Generate and store embeddings for semantic examples
            self._store_semantic_embeddings()
            
            print("✅ S3 Vector Search index initialized successfully")
            
        except Exception as e:
            print(f"❌ Error initializing S3 Vector Search index: {e}")
            raise
    
    def _store_semantic_embeddings(self):
        """Store semantic embeddings in S3 Vector Search format."""
        print("📝 Storing semantic embeddings in S3...")
        
        embeddings_data = []
        
        for semantic_key, examples in self.semantic_examples.items():
            for example in examples:
                # Generate embedding
                embedding = self.model.encode(example)
                
                # Create vector record
                vector_record = {
                    "id": f"{semantic_key}_{example.replace(' ', '_')}",
                    "vector": embedding.tolist(),
                    "metadata": {
                        "semantic_key": semantic_key,
                        "example": example,
                        "type": "semantic_example"
                    }
                }
                
                embeddings_data.append(vector_record)
        
        # Store embeddings in S3
        self.s3_client.put_object(
            Bucket=self.bucket_name,
            Key="vector_index/embeddings.json",
            Body=json.dumps(embeddings_data, indent=2),
            ContentType="application/json"
        )
        
        print(f"✅ Stored {len(embeddings_data)} embeddings in S3")
    
    def search_similar_vectors(self, query_text: str, k: int = 3) -> List[Dict]:
        """
        Search for similar vectors using S3 Vector Search.
        
        Args:
            query_text: The text to search for
            k: Number of top results to return
            
        Returns:
            List of dictionaries containing match information
        """
        try:
            # Generate query embedding
            query_embedding = self.model.encode(query_text)
            
            # Load stored embeddings (in production, this would use S3 Vector Search API)
            embeddings_response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key="vector_index/embeddings.json"
            )
            embeddings_data = json.loads(embeddings_response['Body'].read().decode('utf-8'))
            
            # Calculate similarities (simplified - in production use S3 Vector Search API)
            similarities = []
            for record in embeddings_data:
                vector = np.array(record["vector"])
                similarity = self._cosine_similarity(query_embedding, vector)
                similarities.append({
                    "id": record["id"],
                    "similarity": similarity,
                    "metadata": record["metadata"]
                })
            
            # Sort by similarity and return top k
            similarities.sort(key=lambda x: x["similarity"], reverse=True)
            return similarities[:k]
            
        except Exception as e:
            print(f"❌ Error in vector search: {e}")
            return []
    
    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Calculate cosine similarity between two vectors."""
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        return dot_product / (norm1 * norm2)
    
    def get_landmark_specific_semantic_key(self, question: str, landmark_id: str, 
                                         available_keys: List[str], threshold: float = 0.4) -> Tuple[Optional[str], float]:
        """
        Get the best semantic key for a question using S3 Vector Search.
        
        Args:
            question: The user's question
            landmark_id: The landmark identifier
            available_keys: List of available semantic keys for this landmark type
            threshold: Minimum similarity threshold
            
        Returns:
            Tuple of (best_semantic_key, similarity_score)
        """
        try:
            print(f"🔍 Searching for semantic key for: '{question}'")
            
            # Search for similar vectors
            search_results = self.search_similar_vectors(question, k=5)
            
            best_match = None
            best_score = 0.0
            
            for result in search_results:
                semantic_key = result["metadata"]["semantic_key"]
                example = result["metadata"]["example"]
                similarity = result["similarity"]
                
                # Only consider keys available for this landmark type
                if semantic_key in available_keys:
                    print(f"🔍 Match: {semantic_key} (example: '{example}') - Similarity: {similarity:.3f}")
                    
                    if similarity > best_score:
                        best_score = similarity
                        best_match = semantic_key
            
            if best_match and best_score > threshold:
                print(f"✅ Semantic match: {best_match} (similarity: {best_score:.3f})")
                return best_match, best_score
            else:
                print(f"❌ No confident semantic match found (best: {best_match}, score: {best_score:.3f})")
                return None, None
                
        except Exception as e:
            print(f"🔥 ERROR in S3 Vector Search: {e}")
            return None, None
    
    def add_custom_embedding(self, text: str, semantic_key: str, metadata: Dict = None):
        """
        Add a custom embedding to the S3 Vector Search index.
        
        Args:
            text: The text to embed
            semantic_key: The semantic key for this text
            metadata: Additional metadata
        """
        try:
            # Generate embedding
            embedding = self.model.encode(text)
            
            # Create vector record
            vector_record = {
                "id": f"custom_{semantic_key}_{text.replace(' ', '_')}",
                "vector": embedding.tolist(),
                "metadata": {
                    "semantic_key": semantic_key,
                    "text": text,
                    "type": "custom",
                    **(metadata or {})
                }
            }
            
            # Load existing embeddings
            try:
                embeddings_response = self.s3_client.get_object(
                    Bucket=self.bucket_name,
                    Key="vector_index/embeddings.json"
                )
                embeddings_data = json.loads(embeddings_response['Body'].read().decode('utf-8'))
            except:
                embeddings_data = []
            
            # Add new embedding
            embeddings_data.append(vector_record)
            
            # Store updated embeddings
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key="vector_index/embeddings.json",
                Body=json.dumps(embeddings_data, indent=2),
                ContentType="application/json"
            )
            
            print(f"✅ Added custom embedding for semantic key: {semantic_key}")
            
        except Exception as e:
            print(f"❌ Error adding custom embedding: {e}")
    
    def calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate cosine similarity between two texts."""
        emb1 = self.model.encode(text1)
        emb2 = self.model.encode(text2)
        return float(self._cosine_similarity(emb1, emb2))

# Global instance
s3_vector_search_service = S3VectorSearchService() 