import json
import os
from sentence_transformers import SentenceTransformer, util
from services.s3_vector_search_service import s3_vector_search_service
from typing import List, Optional, Tuple

class SemanticMatchingService:
    def __init__(self):
        self.landmarks_data = self._load_landmarks()
        self.semantic_config = self._load_semantic_config()
        # Use the S3 Vector Search service instead of FAISS
        self.s3_service = s3_vector_search_service
    
    def _load_landmarks(self):
        """Load landmarks metadata."""
        with open("scripts/landmarks.json", "r") as f:
            return json.load(f)
    
    def _load_semantic_config(self):
        """Load semantic configuration."""
        with open("scripts/semantic_config.json", "r") as f:
            return json.load(f)
    
    def calculate_similarity(self, text1, text2):
        """Calculate similarity using S3 Vector Search service."""
        return self.s3_service.calculate_similarity(text1, text2)

    def get_landmark_specific_semantic_key(self, question: str, landmark_id: str, threshold: float = 0.4):
        """
        Get the best semantic key for a question using S3 Vector Search.
        """
        try:
            # 1. Find landmark and get its type
            landmark_type = None
            normalized_landmark_id = landmark_id.lower().replace("_", " ")
            
            # we need to loop here since we need the landmark_type 
            # since it is not passed in the API call
            for landmark in self.landmarks_data:
                landmark_name_lower = landmark["name"].lower()
                if landmark_name_lower == normalized_landmark_id:
                    landmark_type = landmark["type"]
                    break
            
            if not landmark_type:
                print(f"⚠️ Landmark '{landmark_id}' not found in landmarks.json")
                return None, None
            
            # 2. Get available semantic keys for this landmark type
            available_keys = list(self.semantic_config.get(landmark_type, {}).keys())
            print(f"🔍 Landmark: {landmark_id} -> Type: {landmark_type}")
            
            # 3. Use S3 Vector Search semantic matching
            return self.s3_service.get_landmark_specific_semantic_key(
                question=question,
                landmark_id=landmark_id,
                available_keys=available_keys,
                threshold=threshold
            )
                
        except Exception as e:
            print(f"🔥 ERROR in semantic matching: {e}")
            return None, None

# Global instance
semantic_matching_service = SemanticMatchingService() 