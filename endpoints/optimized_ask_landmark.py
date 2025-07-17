from fastapi import HTTPException, Form, File, UploadFile
import uuid
import json
import time
import requests
import boto3
import os
from datetime import datetime
from dotenv import load_dotenv
from services.audio_processing_service import audio_processing_service
from services.advanced_s3_vector_service import advanced_s3_vector_service
from services.llm_service import llm_service
from typing import Dict, Any

# === Load environment variables ===
load_dotenv()

# === Setup DynamoDB ===
dynamodb = boto3.resource(
    'dynamodb',
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name="us-east-2"
)
semantic_table = dynamodb.Table("semantic_responses")

# === Setup S3 ===
s3_client = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION", "us-east-2")
)
S3_BUCKET = os.getenv("S3_BUCKET_NAME")
S3_URL_BASE = os.getenv("S3_URL_BASE")

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

def get_available_semantic_keys(landmark_type: str) -> list:
    """Get available semantic keys for a landmark type."""
    try:
        with open("scripts/semantic_config.json", "r") as f:
            semantic_config = json.load(f)
        
        return list(semantic_config.get(landmark_type, {}).keys())
    except Exception as e:
        print(f"Error getting semantic keys: {e}")
        return ["origin.general"]

async def optimized_ask_landmark_question(
    landmark: str = Form(...),
    userCountry: str = Form("United States"),
    interestOne: str = Form("Nature"),
    userId: str = Form(...),
    audio_file: UploadFile = File(None),
    age: str = Form("25")
):
    """
    Optimized ask-landmark endpoint that maximizes S3 Vector Search benefits.
    Uses multi-layer vector search for better accuracy and performance.
    """
    try:
        # Convert age to integer
        try:
            age_int = int(age) if age else 25
        except (ValueError, TypeError):
            age_int = 25
        
        print(f"🚀 Optimized ask-landmark: {landmark}, {userId}, age: {age_int}")
        
        # 1. Pre-process inputs
        landmark_id = landmark.replace(" ", "_")
        
        # 2. Get question text (from text or audio)
        question_text = None
        if audio_file:
            audio_content = await audio_file.read()
            file_extension = audio_file.filename.split(".")[-1] if "." in audio_file.filename else "m4a"
            question_text = await audio_processing_service.audio_to_text(audio_content, file_extension)
            print(f"🎤 Audio converted: '{question_text}'")
        
        # 3. Get landmark info and available semantic keys
        landmark_type = get_landmark_type(landmark_id)
        available_keys = get_available_semantic_keys(landmark_type)
        city, country = get_landmark_info(landmark_id)
        
        print(f"🏛️ Landmark: {landmark_id} -> Type: {landmark_type}")
        print(f"📍 Location: {city}, {country}")
        print(f"🔑 Available keys: {available_keys}")
        
        # 4. Use Advanced S3 Vector Search for comprehensive answer
        start_time = time.time()
        vector_results = advanced_s3_vector_service.get_comprehensive_answer(
            question=question_text,
            landmark_id=landmark_id,
            available_keys=available_keys,
            user_country=userCountry,
            interest=interestOne,
            age=age_int
        )
        vector_search_time = time.time() - start_time
        
        print(f"⚡ Vector search completed in {vector_search_time:.3f}s")
        print(f"🎯 Search strategy: {vector_results['search_strategy']}")
        print(f"📊 Confidence: {vector_results['confidence']:.3f}")
        
        # 5. Handle different search strategies
        if vector_results["search_strategy"] == "qa_match_landmark_specific":
            # High confidence Q&A match found
            print("✅ Using high-confidence Q&A match")
            
            # Add the Q&A pair to the vector index for future use
            advanced_s3_vector_service.add_qa_pair(
                question=question_text,
                answer=vector_results["best_answer"],
                landmark_id=landmark_id,
                semantic_key=vector_results["semantic_key"],
                metadata={
                    "user_country": userCountry,
                    "interest": interestOne,
                    "age": age_int,
                    "confidence": vector_results["confidence"]
                }
            )
            
            return {
                "status": "success",
                "message": "Retrieved answer from vector database",
                "data": {
                    "answer": vector_results["best_answer"],
                    "source": "s3_vector_qa_match",
                    "confidence": vector_results["confidence"]
                },
                "debug": {
                    "search_strategy": vector_results["search_strategy"],
                    "vector_search_time": vector_search_time,
                    "semantic_key": vector_results["semantic_key"],
                    "qa_matches_count": len(vector_results["qa_matches"]),
                    "fact_matches_count": len(vector_results["fact_matches"])
                }
            }
        
        elif vector_results["search_strategy"] == "fact_match_landmark_specific":
            # Good fact match found
            print("✅ Using fact match")
            
            return {
                "status": "success",
                "message": "Retrieved fact from vector database",
                "data": {
                    "answer": vector_results["best_answer"],
                    "source": "s3_vector_fact_match",
                    "confidence": vector_results["confidence"]
                },
                "debug": {
                    "search_strategy": vector_results["search_strategy"],
                    "vector_search_time": vector_search_time,
                    "fact_matches_count": len(vector_results["fact_matches"])
                }
            }
        
        elif vector_results["search_strategy"] == "semantic_key_match":
            # Semantic key match - generate with LLM
            print("🤖 Using semantic key match with LLM generation")
            
            # Get the prompt template for this semantic key
            prompt_template = get_prompt_template(vector_results["semantic_key"])
            
            if prompt_template:
                # Format the prompt with landmark info
                prompt = prompt_template.format(
                    city=city,
                    country=country,
                    landmark=landmark_id.replace("_", " "),
                    age_group="young" if age_int < 30 else "middleage" if age_int <= 60 else "old",
                    userCountry=userCountry,
                    mappedCategory=interestOne
                )
                
                # Generate response using LLM
                answer = await llm_service.generate_response_with_prompt_and_age(
                    prompt=prompt,
                    question=question_text,
                    landmark_id=landmark_id,
                    user_country=userCountry,
                    interest=interestOne,
                    age_group="young" if age_int < 30 else "middleage" if age_int <= 60 else "old"
                )
            else:
                # Fallback to generic LLM
                answer = await llm_service.generate_response(
                    question=question_text,
                    landmark_id=landmark_id,
                    landmark_type=landmark_type,
                    user_country=userCountry,
                    interest=interestOne
                )
            
            # Add the new Q&A pair to the vector index
            advanced_s3_vector_service.add_qa_pair(
                question=question_text,
                answer=answer,
                landmark_id=landmark_id,
                semantic_key=vector_results["semantic_key"],
                metadata={
                    "user_country": userCountry,
                    "interest": interestOne,
                    "age": age_int,
                    "source": "llm_generated"
                }
            )
            
            # Extract and store facts
            extracted_facts = await extract_facts_from_response(question_text, answer)
            for fact_key, fact_text in extracted_facts.items():
                advanced_s3_vector_service.add_fact(
                    fact_text=fact_text,
                    fact_key=fact_key,
                    landmark_id=landmark_id,
                    metadata={
                        "user_country": userCountry,
                        "interest": interestOne,
                        "source": "llm_extracted"
                    }
                )
            
            return {
                "status": "success",
                "message": "Generated answer using LLM with semantic key",
                "data": {
                    "answer": answer,
                    "source": "llm_semantic_key_match",
                    "confidence": vector_results["confidence"]
                },
                "debug": {
                    "search_strategy": vector_results["search_strategy"],
                    "vector_search_time": vector_search_time,
                    "semantic_key": vector_results["semantic_key"],
                    "extracted_facts_count": len(extracted_facts)
                }
            }
        
        else:
            # No good matches found - use generic LLM
            print("🤖 No vector matches found, using generic LLM")
            
            answer = await llm_service.generate_response(
                question=question_text,
                landmark_id=landmark_id,
                landmark_type=landmark_type,
                user_country=userCountry,
                interest=interestOne
            )
            
            # Add to vector index for future use
            advanced_s3_vector_service.add_qa_pair(
                question=question_text,
                answer=answer,
                landmark_id=landmark_id,
                semantic_key="general",
                metadata={
                    "user_country": userCountry,
                    "interest": interestOne,
                    "age": age_int,
                    "source": "llm_generic"
                }
            )
            
            return {
                "status": "success",
                "message": "Generated answer using generic LLM",
                "data": {
                    "answer": answer,
                    "source": "llm_generic",
                    "confidence": 0.0
                },
                "debug": {
                    "search_strategy": vector_results["search_strategy"],
                    "vector_search_time": vector_search_time
                }
            }
        
    except Exception as e:
        print(f"❌ Error in optimized ask-landmark: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process question: {str(e)}")

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

async def extract_facts_from_response(question: str, answer: str) -> dict:
    """Extract facts from LLM response."""
    try:
        fact_extraction_prompt = f"""
        Extract key facts from this answer about the landmark. Return only the facts as a JSON object with descriptive keys.
        
        Question: {question}
        Answer: {answer}
        
        Return format: {{"fact1": "description", "fact2": "description"}}
        """
        
        facts_response = await llm_service.generate_response(
            question=fact_extraction_prompt,
            landmark_id="fact_extraction",
            landmark_type="general",
            user_country="United States",
            interest="general"
        )
        
        # Try to parse JSON from response
        try:
            start_idx = facts_response.find('{')
            end_idx = facts_response.rfind('}') + 1
            if start_idx != -1 and end_idx > start_idx:
                json_str = facts_response[start_idx:end_idx]
                extracted_facts = json.loads(json_str)
            else:
                extracted_facts = {"general_info": answer[:100] + "..."}
        except json.JSONDecodeError:
            extracted_facts = {"general_info": answer[:100] + "..."}
        
        return extracted_facts
        
    except Exception as e:
        print(f"Error extracting facts: {e}")
        return {"general_info": answer[:100] + "..."} 