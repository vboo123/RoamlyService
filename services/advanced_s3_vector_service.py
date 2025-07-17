import json
import os
import boto3
import numpy as np
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Optional, Tuple, Any
from dotenv import load_dotenv
from datetime import datetime
import uuid

# Load environment variables
load_dotenv()

class AdvancedS3VectorService:
    """
    Advanced S3 Vector Search service with per-landmark file structure.
    Optimized for scalability with separate files per landmark.
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
        
        print("🔧 S3 Vector Search service initialized")
    
    def _create_landmark_semantic_key_index(self, landmark_id: str, landmark_type: str):
        """Create landmark-specific semantic key index based on landmark type."""
        
        # Define semantic key examples for each landmark type
        semantic_examples = {
            "religious": {
                "origin.general": [
                    "how did it come to be", "when was it built", "how was it created",
                    "what's the history", "origin story", "when was this built",
                    "how did this get here", "what's the story behind this"
                ],
                "origin.name": [
                    "what does the name mean", "why is it called", "name origin",
                    "meaning of the name", "how did it get its name"
                ],
                "culture.symbolism": [
                    "symbols", "meaning", "symbolism", "cultural significance",
                    "what does it represent", "what's the meaning", "cultural meaning"
                ],
                "myths.legends": [
                    "myths", "legends", "stories", "folklore", "tales",
                    "urban legends", "mythical stories", "legendary tales"
                ],
                "architecture.style": [
                    "what style is it", "architecture", "design", "how does it look",
                    "architectural features", "architectural style", "what kind of building"
                ],
                "experience.vibe": [
                    "what's the vibe", "atmosphere", "feel", "mood",
                    "what's it like", "how does it feel", "what's the atmosphere like"
                ],
                "access.crowds": [
                    "crowds", "busy", "crowded", "people", "visitors",
                    "how many people", "how crowded", "how busy", "how many visitors"
                ],
                "access.hours": [
                    "hours", "opening times", "when open", "schedule",
                    "what time does it open", "when is it open", "what are the hours"
                ],
                "access.parking": [
                    "parking", "where to park", "parking options", "parking cost",
                    "is there parking", "parking availability"
                ],
                "access.transport": [
                    "how to get there", "transportation", "public transit", "bus",
                    "subway", "walking directions", "how to reach"
                ],
                "culture.photography": [
                    "photo spots", "best angles", "photography", "pictures",
                    "where to take photos", "photo opportunities"
                ],
                "recreation.nearby": [
                    "nearby activities", "things to do nearby", "recreation",
                    "parks nearby", "outdoor activities", "what's around"
                ],
                "dining.nearby": [
                    "restaurants nearby", "food options", "places to eat",
                    "dining", "cafes", "where to eat"
                ],
                "culture.events": [
                    "events", "services", "ceremonies", "festivals",
                    "what happens here", "activities", "programs"
                ],
                "history.timeline": [
                    "timeline", "history", "when was it built", "historical events",
                    "past events", "chronology", "historical timeline"
                ]
            },
            "educational": {
                "origin.general": [
                    "how did it come to be", "when was it built", "how was it created",
                    "what's the history", "origin story", "when was this built"
                ],
                "architecture.style": [
                    "what style is it", "architecture", "design", "how does it look"
                ],
                "access.hours": [
                    "hours", "opening times", "when open", "schedule"
                ],
                "access.cost": [
                    "how much", "cost", "price", "ticket", "entry fee"
                ],
                "experience.vibe": [
                    "what's the vibe", "atmosphere", "feel", "mood"
                ],
                "access.crowds": [
                    "crowds", "busy", "crowded", "people", "visitors"
                ],
                "history.timeline": [
                    "timeline", "history", "when was it built", "historical events"
                ]
            },
            "historical": {
                "origin.general": [
                    "how did it come to be", "when was it built", "how was it created",
                    "what's the history", "origin story", "when was this built"
                ],
                "architecture.style": [
                    "what style is it", "architecture", "design", "how does it look"
                ],
                "history.timeline": [
                    "timeline", "history", "when was it built", "historical events"
                ],
                "culture.events": [
                    "events", "ceremonies", "festivals", "what happens here"
                ],
                "access.hours": [
                    "hours", "opening times", "when open", "schedule"
                ],
                "access.cost": [
                    "how much", "cost", "price", "ticket", "entry fee"
                ],
                "experience.vibe": [
                    "what's the vibe", "atmosphere", "feel", "mood"
                ]
            }
        }
        
        # Get semantic keys for this landmark type
        type_examples = semantic_examples.get(landmark_type, semantic_examples["historical"])
        
        # Store landmark-specific semantic key index
        self._store_landmark_semantic_key_vectors(landmark_id, type_examples)
        
        print(f"✅ Created semantic key index for {landmark_id} (type: {landmark_type})")
    
    def _store_landmark_semantic_key_vectors(self, landmark_id: str, semantic_examples: Dict):
        """Store landmark-specific semantic key vectors."""
        vectors = []
        
        for key, examples in semantic_examples.items():
            for example in examples:
                embedding = self.model.encode(example)
                vector_record = {
                    "id": f"semantic_key_{landmark_id}_{key}_{example.replace(' ', '_')}",
                    "vector": embedding.tolist(),
                    "metadata": {
                        "type": "semantic_key",
                        "landmark_id": landmark_id,
                        "key": key,
                        "text": example,
                        "index_name": "semantic_key_index"
                    }
                }
                vectors.append(vector_record)
        
        # Store in landmark-specific folder
        self._store_landmark_vectors(landmark_id, "semantic_key_index", vectors)
    
    def _store_landmark_vectors(self, landmark_id: str, index_name: str, vectors: List[Dict]):
        """Store landmark-specific vectors in S3."""
        try:
            # Create landmark folder structure
            s3_key = f"vector-search/landmarks/{landmark_id}/{index_name}.json"
            
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=json.dumps(vectors, indent=2),
                ContentType="application/json"
            )
            
            print(f"✅ Stored {len(vectors)} vectors in {landmark_id}/{index_name}")
            
        except Exception as e:
            print(f"❌ Error storing landmark vectors: {e}")
    
    def _load_landmark_vectors(self, landmark_id: str, index_name: str) -> List[Dict]:
        """Load landmark-specific vectors from S3."""
        try:
            s3_key = f"vector-search/landmarks/{landmark_id}/{index_name}.json"
            
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            
            vectors = json.loads(response['Body'].read().decode('utf-8'))
            return vectors
            
        except Exception as e:
            print(f"⚠️ No vectors found for {landmark_id}/{index_name}: {e}")
            return []
    

    
    def search_semantic_key(self, question: str, landmark_id: str, available_keys: List[str], threshold: float = 0.4) -> Tuple[Optional[str], float]:
        """Search for semantic key classification using landmark-specific index."""
        try:
            # Load landmark-specific semantic key index
            vectors = self._load_landmark_vectors(landmark_id, "semantic_key_index")
            
            if not vectors:
                print(f"⚠️ No semantic key index found for {landmark_id}")
                return None, 0.0
            
            # Search for best match
            query_embedding = self.model.encode(question)
            best_match = None
            best_score = 0.0
            
            for vector_record in vectors:
                vector = np.array(vector_record["vector"])
                similarity = self._cosine_similarity(query_embedding, vector)
                
                semantic_key = vector_record["metadata"]["key"]
                if semantic_key in available_keys and similarity > best_score:
                    best_score = similarity
                    best_match = semantic_key
            
            if best_match and best_score > threshold:
                return best_match, best_score
            return None, 0.0
            
        except Exception as e:
            print(f"❌ Error in semantic key search: {e}")
            return None, 0.0
    
    def search_qa_pairs(self, question: str, landmark_id: str, user_country: str = None, 
                       interest: str = None, age: int = None, k: int = 3) -> List[Dict]:
        """Search for similar Q&A pairs within a specific landmark."""
        try:
            # Load landmark-specific Q&A index
            vectors = self._load_landmark_vectors(landmark_id, "qa_index")
            
            if not vectors:
                return []
            
            # Search for similar questions
            query_embedding = self.model.encode(question)
            similarities = []
            
            for vector_record in vectors:
                vector = np.array(vector_record["vector"])
                similarity = self._cosine_similarity(query_embedding, vector)
                
                # Calculate personalization bonus
                personalization_bonus = 0.0
                
                # Country matching bonus
                if user_country and vector_record["metadata"].get("user_country") == user_country:
                    personalization_bonus += 0.1
                
                # Interest matching bonus
                if interest and vector_record["metadata"].get("interest") == interest:
                    personalization_bonus += 0.1
                
                # Age matching bonus
                if age:
                    age_group = "young" if age < 30 else "middleage" if age <= 60 else "old"
                    if vector_record["metadata"].get("age_group") == age_group:
                        personalization_bonus += 0.05
                
                # Apply personalization bonus
                final_similarity = similarity + personalization_bonus
                
                similarities.append({
                    "question": vector_record["metadata"]["question"],
                    "answer": vector_record["metadata"]["answer"],
                    "similarity": final_similarity,
                    "semantic_key": vector_record["metadata"].get("semantic_key"),
                    "personalization_bonus": personalization_bonus
                })
            
            # Sort by similarity and return top k
            similarities.sort(key=lambda x: x["similarity"], reverse=True)
            return similarities[:k]
            
        except Exception as e:
            print(f"❌ Error in Q&A search: {e}")
            return []
    
    def add_qa_pair(self, question: str, answer: str, landmark_id: str, semantic_key: str, metadata: Dict = None):
        """Add a Q&A pair to landmark-specific index."""
        try:
            # Load existing Q&A vectors
            vectors = self._load_landmark_vectors(landmark_id, "qa_index")
            
            # Create new vector record
            embedding = self.model.encode(question)
            vector_record = {
                "id": f"qa_{landmark_id}_{semantic_key}_{uuid.uuid4().hex[:8]}",
                "vector": embedding.tolist(),
                "metadata": {
                    "type": "qa_pair",
                    "landmark_id": landmark_id,
                    "semantic_key": semantic_key,
                    "question": question,
                    "answer": answer,
                    **(metadata or {})
                }
            }
            
            vectors.append(vector_record)
            
            # Store updated vectors
            self._store_landmark_vectors(landmark_id, "qa_index", vectors)
            
            print(f"✅ Added Q&A pair for {landmark_id} - {semantic_key}")
            
        except Exception as e:
            print(f"❌ Error adding Q&A pair: {e}")
    
    def add_fact(self, fact_text: str, fact_key: str, landmark_id: str, metadata: Dict = None):
        """Add a fact to landmark-specific index."""
        try:
            # Load existing fact vectors
            vectors = self._load_landmark_vectors(landmark_id, "fact_index")
            
            # Create new vector record
            embedding = self.model.encode(fact_text)
            vector_record = {
                "id": f"fact_{landmark_id}_{fact_key}_{uuid.uuid4().hex[:8]}",
                "vector": embedding.tolist(),
                "metadata": {
                    "type": "fact",
                    "landmark_id": landmark_id,
                    "fact_key": fact_key,
                    "fact_text": fact_text,
                    **(metadata or {})
                }
            }
            
            vectors.append(vector_record)
            
            # Store updated vectors
            self._store_landmark_vectors(landmark_id, "fact_index", vectors)
            
            print(f"✅ Added fact for {landmark_id} - {fact_key}")
            
        except Exception as e:
            print(f"❌ Error adding fact: {e}")
    
    def search_facts(self, query: str, landmark_id: str, k: int = 3) -> List[Dict]:
        """Search for relevant facts within a specific landmark."""
        try:
            # Load landmark-specific fact index
            vectors = self._load_landmark_vectors(landmark_id, "fact_index")
            
            if not vectors:
                return []
            
            # Search for similar facts
            query_embedding = self.model.encode(query)
            similarities = []
            
            for vector_record in vectors:
                vector = np.array(vector_record["vector"])
                similarity = self._cosine_similarity(query_embedding, vector)
                
                similarities.append({
                    "fact_key": vector_record["metadata"]["fact_key"],
                    "fact_text": vector_record["metadata"]["fact_text"],
                    "similarity": similarity,
                    "semantic_key": vector_record["metadata"].get("semantic_key")
                })
            
            # Sort by similarity and return top k
            similarities.sort(key=lambda x: x["similarity"], reverse=True)
            return similarities[:k]
            
        except Exception as e:
            print(f"❌ Error in fact search: {e}")
            return []
    
    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Calculate cosine similarity between two vectors."""
        return float(np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2)))
    
    def calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two texts."""
        emb1 = self.model.encode(text1)
        emb2 = self.model.encode(text2)
        return float(self._cosine_similarity(emb1, emb2))
    
    def get_landmark_response(self, landmark_id: str, semantic_key: str, user_country: str, 
                            interest: str, age: int) -> Dict[str, Any]:
        """
        Get personalized landmark response using landmark-specific index.
        """
        try:
            # Load landmark-specific index
            vectors = self._load_landmark_vectors(landmark_id, "landmark_specific_index")
            
            if not vectors:
                return {
                    "status": "not_found",
                    "message": "No responses found for this landmark"
                }
            
            # Filter by semantic key
            relevant_vectors = [
                v for v in vectors 
                if v["metadata"].get("semantic_key") == semantic_key
            ]
            
            if not relevant_vectors:
                return {
                    "status": "not_found",
                    "message": "No responses found for this landmark and semantic key"
                }
            
            # Find best personalized response
            age_group = "young" if age < 30 else "middleage" if age <= 60 else "old"
            best_response = None
            best_score = 0.0
            
            for vector_record in relevant_vectors:
                score = 0.0
                
                # Country match
                if vector_record["metadata"].get("user_country") == user_country:
                    score += 3.0
                elif vector_record["metadata"].get("user_country") == "default":
                    score += 1.0
                
                # Interest match
                if vector_record["metadata"].get("interest") == interest:
                    score += 2.0
                elif vector_record["metadata"].get("interest") == "default":
                    score += 0.5
                
                # Age group match
                if vector_record["metadata"].get("age_group") == age_group:
                    score += 1.0
                elif vector_record["metadata"].get("age_group") == "default":
                    score += 0.5
                
                if score > best_score:
                    best_score = score
                    best_response = vector_record["metadata"]["response"]
            
            if best_response:
                return {
                    "status": "success",
                    "landmark": landmark_id.replace("_", " "),
                    "semantic_key": semantic_key,
                    "country": user_country,
                    "interest": interest,
                    "age": age,
                    "age_group": age_group,
                    "response": best_response,
                    "personalization_score": best_score
                }
            else:
                return {
                    "status": "not_found",
                    "message": "No personalized response found"
                }
                
        except Exception as e:
            print(f"❌ Error in landmark response: {e}")
            return {
                "status": "error",
                "message": f"Failed to get landmark response: {str(e)}"
            }
    
    def add_landmark_response(self, landmark_id: str, semantic_key: str, response: str,
                            user_country: str, interest: str, age: int, metadata: Dict = None):
        """
        Add a landmark response to landmark-specific index.
        """
        try:
            # Load existing landmark-specific vectors
            vectors = self._load_landmark_vectors(landmark_id, "landmark_specific_index")
            
            # Create new vector record
            age_group = "young" if age < 30 else "middleage" if age <= 60 else "old"
            
            # Create a generic question for this semantic key
            semantic_questions = {
                "origin.general": "Tell me about this landmark",
                "height.general": "What's the height of this landmark", 
                "access.cost": "How much does it cost to visit",
                "access.hours": "What are the opening hours",
                "architecture.style": "What's the architectural style",
                "culture.symbolism": "What's the cultural significance",
                "experience.vibe": "What's the atmosphere like",
                "myths.legends": "Are there any myths or legends"
            }
            
            question = semantic_questions.get(semantic_key, f"Tell me about {semantic_key}")
            embedding = self.model.encode(question)
            
            vector_record = {
                "id": f"landmark_response_{landmark_id}_{semantic_key}_{user_country}_{interest}_{age}",
                "vector": embedding.tolist(),
                "metadata": {
                    "type": "landmark_specific",
                    "landmark_id": landmark_id,
                    "semantic_key": semantic_key,
                    "user_country": user_country,
                    "interest": interest,
                    "age": age,
                    "age_group": age_group,
                    "response": response,
                    "response_type": "default",
                    **(metadata or {})
                }
            }
            
            vectors.append(vector_record)
            
            # Store updated vectors
            self._store_landmark_vectors(landmark_id, "landmark_specific_index", vectors)
            
            print(f"✅ Added landmark response for {landmark_id} - {semantic_key}")
            
        except Exception as e:
            print(f"❌ Error adding landmark response: {e}")
    
    def get_comprehensive_answer(self, question: str, landmark_id: str, available_keys: List[str],
                              user_country: str = None, interest: str = None, age: int = None) -> Dict[str, Any]:
        """
        Get comprehensive answer using landmark-specific vector search.
        """
        try:
            results = {
                "semantic_key": None,
                "qa_matches": [],
                "fact_matches": [],
                "best_answer": None,
                "confidence": 0.0,
                "search_strategy": "landmark_specific"
            }
            
            # 1. First, try semantic key classification using landmark-specific index
            semantic_key, semantic_confidence = self.search_semantic_key(question, landmark_id, available_keys)
            results["semantic_key"] = semantic_key
            results["confidence"] = semantic_confidence
            
            # 2. Search for similar Q&A pairs within this landmark
            qa_matches = self.search_qa_pairs(
                question=question,
                landmark_id=landmark_id,
                user_country=user_country,
                interest=interest,
                age=age,
                k=3
            )
            results["qa_matches"] = qa_matches
            
            # 3. Search for relevant facts within this landmark
            fact_matches = self.search_facts(question, landmark_id, k=3)
            results["fact_matches"] = fact_matches
            
            # 4. Determine best answer strategy
            if qa_matches and qa_matches[0]["similarity"] > 0.7:
                # High confidence Q&A match
                results["best_answer"] = qa_matches[0]["answer"]
                results["confidence"] = qa_matches[0]["similarity"]
                results["search_strategy"] = "qa_match_landmark_specific"
            elif fact_matches and fact_matches[0]["similarity"] > 0.6:
                # Good fact match
                results["best_answer"] = fact_matches[0]["fact_text"]
                results["confidence"] = fact_matches[0]["similarity"]
                results["search_strategy"] = "fact_match_landmark_specific"
            elif semantic_confidence > 0.4:
                # Semantic key match - will need LLM generation
                results["search_strategy"] = "semantic_key_match"
            else:
                # No good matches found
                results["search_strategy"] = "no_match"
            
            return results
            
        except Exception as e:
            print(f"❌ Error in comprehensive answer search: {e}")
            return {
                "semantic_key": None,
                "qa_matches": [],
                "fact_matches": [],
                "best_answer": None,
                "confidence": 0.0,
                "search_strategy": "error"
            }

# Global instance
advanced_s3_vector_service = AdvancedS3VectorService() 