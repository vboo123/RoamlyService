import json
import os
from sentence_transformers import SentenceTransformer, util
import faiss
import numpy as np

class SemanticMatchingService:
    def __init__(self):
        self.landmarks_data = self._load_landmarks()
        self.semantic_config = self._load_semantic_config()
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        self.dimension = 384
        self.index = None
        self.metadata = []
        self._build_faiss_index()
    
    def _load_landmarks(self):
        """Load landmarks metadata."""
        with open("scripts/landmarks.json", "r") as f:
            return json.load(f)
    
    def _load_semantic_config(self):
        """Load semantic configuration."""
        with open("scripts/semantic_config.json", "r") as f:
            return json.load(f)
    
    def _build_faiss_index(self):
        """Build FAISS index with semantic key examples."""
        print("🔧 Building FAISS semantic index...")
        
        # Define semantic key examples with multiple variations
        semantic_examples = {
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
        
        # Build vectors and metadata
        vectors = []
        self.metadata = []
        
        for semantic_key, examples in semantic_examples.items():
            for example in examples:
                emb = self.model.encode(example)
                vectors.append(emb)
                self.metadata.append({
                    "semantic_key": semantic_key,
                    "example": example
                })
        
        # Create FAISS index
        self.index = faiss.IndexFlatL2(self.dimension)
        self.index.add(np.array(vectors).astype('float32'))
        
        print(f"✅ FAISS index built with {len(self.metadata)} semantic examples")
    
    def get_landmark_specific_semantic_key(self, question: str, landmark_id: str, threshold: float = 0.4):
        """
        Get the best semantic key for a question using FAISS-based semantic matching.
        """
        try:
            # 1. Find landmark and get its type
            landmark_type = None
            normalized_landmark_id = landmark_id.lower().replace("_", " ")
            
            for landmark in self.landmarks_data:
                landmark_name_lower = landmark["name"].lower()
                if landmark_name_lower == normalized_landmark_id:
                    landmark_type = landmark["type"]
                    break
            
            if not landmark_type:
                print(f"⚠️ Landmark '{landmark_id}' not found in landmarks.json")
                print(f"🔍 Looking for: '{normalized_landmark_id}'")
                print(f"📋 Available landmarks: {[l['name'] for l in self.landmarks_data]}")
                return None, None
            
            # 2. Get available semantic keys for this landmark type
            available_keys = list(self.semantic_config.get(landmark_type, {}).keys())
            print(f"🔍 Landmark: {landmark_id} -> Type: {landmark_type}")
            print(f"📋 Available keys: {available_keys}")
            
            # 3. Use FAISS semantic matching
            question_emb = self.model.encode(question).reshape(1, -1).astype('float32')
            D, I = self.index.search(question_emb, k=3)  # Get top 3 matches
            
            best_match = None
            best_score = 0.0  # Start with 0, higher similarity is better
            
            for i, (distance, idx) in enumerate(zip(D[0], I[0])):
                match = self.metadata[idx]
                semantic_key = match["semantic_key"]
                example = match["example"]
                
                # Only consider keys available for this landmark type
                if semantic_key in available_keys:
                    # Convert L2 distance to similarity score (0-1, higher is better)
                    similarity_score = 1.0 / (1.0 + distance)
                    
                    print(f"🔍 Match {i+1}: {semantic_key} (example: '{example}') - Distance: {distance:.3f}, Similarity: {similarity_score:.3f}")
                    
                    if similarity_score > best_score:
                        best_score = similarity_score
                        best_match = semantic_key
            
            if best_match and best_score > threshold:
                print(f"✅ Semantic match: {best_match} (similarity: {best_score:.3f})")
                return best_match, best_score
            else:
                print(f"❌ No confident semantic match found (best: {best_match}, score: {best_score:.3f})")
                return None, None
                
        except Exception as e:
            print(f"🔥 ERROR in semantic matching: {e}")
            return None, None

# Global instance
semantic_matching_service = SemanticMatchingService() 