from fastapi import HTTPException, Query, Depends, Request
import json
import os
from datetime import datetime
from dotenv import load_dotenv
from services.advanced_s3_vector_service import advanced_s3_vector_service
from utils.age_utils import AgeUtils

# === Load environment variables ===
load_dotenv()

# Import get_current_user from app.py
def get_current_user(request: Request):
    """Dependency for getting current user (reuse from app.py)."""
    from app import get_current_user as app_get_current_user
    return app_get_current_user(request)

async def enhanced_landmark_response(
    landmark: str,
    request: Request,
    user=Depends(get_current_user),
    interest: str = Query("Nature", alias="interest[]"),
    userCountry: str = "United States",
    semanticKey: str = "origin.general",
    age: int = 25
):
    """
    Enhanced landmark-response endpoint using S3 Vector Search.
    Preserves the original functionality while leveraging vector search benefits.
    """
    try:
        print(f"🔍 Enhanced landmark-response: {landmark}, {userCountry}, {interest}, {semanticKey}, {age}")
        
        # Normalize input
        landmark_id = landmark.replace(" ", "_")
        
        # Use interest directly since it's now a string
        user_interest = interest if interest else "Nature"
        
        # Classify age
        age_group = AgeUtils.classify_age(age)

        # Use S3 Vector Search to get personalized landmark response
        response_result = advanced_s3_vector_service.get_landmark_response(
            landmark_id=landmark_id,
            semantic_key=semanticKey,
            user_country=userCountry,
            interest=user_interest,
            age=age
        )
        
        if response_result["status"] == "success":
            # Found a personalized response
            return {
                "landmark": landmark_id,
                "semantic_key": semanticKey,
                "country": userCountry,
                "interest": user_interest,
                "age": age,
                "age_group": age_group,
                "response": response_result["response"],
                "source": "s3_vector_personalized",
                "personalization_score": response_result["personalization_score"]
            }
        else:
            # No personalized response found - fallback to LLM generation
            print(f"⚠️ No personalized response found, generating with LLM")
            
            # Get landmark info for LLM generation
            city, country = get_landmark_info(landmark_id)
            landmark_type = get_landmark_type(landmark_id)
            
            # Get prompt template
            prompt_template = get_prompt_template(semanticKey)
            
            if prompt_template:
                # Format the prompt with landmark info
                prompt = prompt_template.format(
                    city=city,
                    country=country,
                    landmark=landmark_id.replace("_", " "),
                    age_group=age_group,
                    userCountry=userCountry,
                    mappedCategory=user_interest
                )
                
                # Generate response using LLM
                from services.llm_service import llm_service
                answer = await llm_service.generate_response_with_prompt_and_age(
                    prompt=prompt,
                    question=f"Tell me about {semanticKey}",
                    landmark_id=landmark_id,
                    user_country=userCountry,
                    interest=user_interest,
                    age_group=age_group
                )
                
                # Store the generated response for future use
                advanced_s3_vector_service.add_landmark_response(
                    landmark_id=landmark_id,
                    semantic_key=semanticKey,
                    response=answer,
                    user_country=userCountry,
                    interest=user_interest,
                    age=age,
                    metadata={
                        "generated_at": datetime.utcnow().isoformat(),
                        "source": "llm_generated"
                    }
                )
                
                return {
                    "landmark": landmark_id,
                    "semantic_key": semanticKey,
                    "country": userCountry,
                    "interest": user_interest,
                    "age": age,
                    "age_group": age_group,
                    "response": answer,
                    "source": "llm_generated",
                    "personalization_score": 0.0
                }
            else:
                raise HTTPException(status_code=404, detail="No response template found")

    except Exception as e:
        print("🔥 ERROR in enhanced landmark-response:", e)
        raise HTTPException(status_code=500, detail=f"Failed to fetch landmark response: {str(e)}")

def get_landmark_info(landmark_id: str) -> tuple:
    """Get landmark city and country from landmarks.json."""
    try:
        with open("scripts/landmarks.json", "r") as f:
            landmarks = json.load(f)
        
        for landmark in landmarks:
            if landmark["name"].lower().replace(" ", "_") == landmark_id.lower():
                return landmark.get("city", "a city"), landmark.get("country", "a country")
        
        return "a city", "a country"
    except Exception as e:
        print(f"Error getting landmark info: {e}")
        return "a city", "a country"

def get_landmark_type(landmark_id: str) -> str:
    """Get landmark type from landmarks.json."""
    try:
        with open("scripts/landmarks.json", "r") as f:
            landmarks = json.load(f)
        
        for landmark in landmarks:
            if landmark["name"].lower().replace(" ", "_") == landmark_id.lower():
                return landmark.get("type", "tourist_attraction")
        
        return "tourist_attraction"
    except Exception as e:
        print(f"Error getting landmark type: {e}")
        return "tourist_attraction"

def get_prompt_template(semantic_key: str) -> str:
    """Get prompt template for a semantic key."""
    try:
        with open("scripts/semantic_config.json", "r") as f:
            semantic_config = json.load(f)
        
        # Search through all landmark types for the semantic key
        for landmark_type, keys in semantic_config.items():
            if semantic_key in keys:
                return keys[semantic_key]
        
        return None
    except Exception as e:
        print(f"Error getting prompt template: {e}")
        return None 