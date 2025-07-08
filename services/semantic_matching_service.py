import json
import os

class SemanticMatchingService:
    def __init__(self):
        self.landmarks_data = self._load_landmarks()
        self.semantic_config = self._load_semantic_config()
        self.keyword_mappings = self._get_keyword_mappings()
    
    def _load_landmarks(self):
        """Load landmarks metadata."""
        with open("scripts/landmarks.json", "r") as f:
            return json.load(f)
    
    def _load_semantic_config(self):
        """Load semantic configuration."""
        with open("scripts/semantic_config.json", "r") as f:
            return json.load(f)
    
    def _get_keyword_mappings(self):
        """Define keyword mappings for semantic keys."""
        return {
            "origin.general": ["how did it come to be", "when was it built", "how was it created", "what's the history", "origin story"],
            "origin.name": ["name meaning", "why called", "naming", "name origin", "what does the name mean"],
            "architecture.style": ["what style is it", "architecture", "design", "how does it look", "architectural features", "architectural style"],
            "height.general": ["how tall", "height", "how high", "tallness", "elevation"],
            "experience.vibe": ["what's the vibe", "atmosphere", "feel", "mood", "what's it like"],
            "access.cost": ["how much", "cost", "price", "ticket", "entry fee"],
            "access.hours": ["hours", "opening times", "when open", "schedule"],
            "culture.symbolism": ["symbols", "meaning", "symbolism", "cultural significance"],
            "myths.legends": ["myths", "legends", "stories", "folklore", "tales"],
            "access.crowds": ["crowds", "busy", "crowded", "people", "visitors"]
        }
    
    def get_landmark_specific_semantic_key(self, question: str, landmark_id: str, threshold: float = 0.7):
        """
        Get the best semantic key for a question, using existing metadata structure.
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
            
            # 3. Simple keyword matching
            question_lower = question.lower()
            
            # 4. Find matching semantic key
            best_match = None
            best_score = 0
            
            for semantic_key in available_keys:
                if semantic_key in self.keyword_mappings:
                    keywords = self.keyword_mappings[semantic_key]
                    for keyword in keywords:
                        if keyword in question_lower:
                            # Simple scoring: longer keyword matches get higher scores
                            score = len(keyword) / len(question_lower)
                            if score > best_score:
                                best_score = score
                                best_match = semantic_key
            
            if best_match and best_score > 0.1:  # Threshold for keyword matching
                print(f"✅ Keyword match: {best_match} (score: {best_score:.3f})")
                return best_match, best_score
            else:
                print(f"❌ No keyword match found")
                return None, None
                
        except Exception as e:
            print(f"🔥 ERROR in semantic matching: {e}")
            return None, None

# Global instance
semantic_matching_service = SemanticMatchingService() 