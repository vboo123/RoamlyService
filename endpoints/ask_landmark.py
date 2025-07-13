from fastapi import HTTPException, Form, File, UploadFile
import uuid
import json
import time
import requests
import boto3
import os
from dotenv import load_dotenv
from services.audio_processing_service import audio_processing_service
from services.semantic_matching_service import semantic_matching_service
from services.llm_service import llm_service

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

# === Session Store (In-Memory for MVP) ===
session_store = {}

async def ask_landmark_question(
    landmark: str = Form(...),
    question: str = Form(None),
    userCountry: str = Form("United States"),
    interestOne: str = Form("Nature"),
    userId: str = Form(...),
    sessionId: str = Form(None),
    audio_file: UploadFile = File(None)
):
    """
    Handle follow-up questions with session management and intelligent response routing
    """
    try:
        print(f"🎯 Processing ask-landmark request: {landmark}, {userId}, {sessionId}")
        
        # 1. Pre-process inputs
        landmark_id = landmark.replace(" ", "_")
        
        # Normalize country mapping
        country_map = {
            "UnitedStatesofAmerica": "United States",
            "USA": "United States",
            "US": "United States"
        }
        userCountry = country_map.get(userCountry, userCountry)
        
        # 2. Get question text (from text or audio)
        question_text = None
        if audio_file:
            print(f"🎤 Processing audio file: {audio_file.filename}")
            audio_content = await audio_file.read()
            file_extension = audio_file.filename.split(".")[-1] if "." in audio_file.filename else "m4a"
            question_text = await audio_processing_service.audio_to_text(audio_content, file_extension)
            print(f" Audio converted to question: '{question_text}'")
        elif question:
            question_text = question
            print(f"📝 Processing text question: '{question_text}'")
        else:
            raise HTTPException(status_code=400, detail="Either question or audio_file must be provided")
        
        # 3. Session management
        session_key = f"{userId}:{sessionId}" if sessionId else f"{userId}:{str(uuid.uuid4())}"
        session_data = get_or_initialize_session(session_key, userId, sessionId, landmark_id)
        
        # 4. Semantic key mapping
        semantic_key, confidence = semantic_matching_service.get_landmark_specific_semantic_key(
            question_text, landmark_id
        )
        
        print(f"🔍 Semantic mapping result: {semantic_key} (confidence: {confidence})")
        
        if semantic_key and confidence > 0.4:  # High confidence threshold
            # 5. Handle successful semantic key mapping
            return await handle_successful_semantic_mapping(
                landmark_id, semantic_key, question_text, userCountry, 
                interestOne, session_data, session_key
            )
        else:
            # 6. Handle unsuccessful semantic key mapping (LLM fallback)
            return await handle_llm_fallback(
                landmark_id, question_text, userCountry, interestOne, 
                session_data, session_key
            )
            
    except Exception as e:
        print(" ERROR in /ask-landmark:", e)
        raise HTTPException(status_code=500, detail=f"Failed to process question: {str(e)}")

def get_or_initialize_session(session_key: str, userId: str, sessionId: str, landmark_id: str) -> dict:
    """Get existing session or initialize new one"""
    if session_key in session_store:
        session_data = session_store[session_key]
        # Update last activity
        session_data["lastActivityTime"] = time.time()
        return session_data
    else:
        # Initialize new session
        new_session_id = sessionId or str(uuid.uuid4())
        session_data = {
            "sessionId": new_session_id,
            "userId": userId,
            "currentLandmarkId": landmark_id,
            "semanticKeyInteractionHistory": {},
            "lastQuestionOverall": None,
            "lastAnswerOverall": None,
            "lastSemanticKeyOverall": None,
            "sessionStartTime": time.time(),
            "lastActivityTime": time.time()
        }
        session_store[session_key] = session_data
        return session_data

async def handle_successful_semantic_mapping(
    landmark_id: str, semantic_key: str, question_text: str, 
    userCountry: str, interestOne: str, session_data: dict, session_key: str
):
    """Handle successful semantic key mapping with structured data retrieval"""
    try:
        print(f"✅ Found semantic key: {semantic_key}")
        
        # Query the semantic_responses table
        response = semantic_table.get_item(
            Key={
                "landmark_id": landmark_id,
                "semantic_key": semantic_key
            }
        )
        
        item = response.get("Item")
        if not item:
            print(f"⚠️ No data found for semantic key: {semantic_key}")
            return await handle_llm_fallback(
                landmark_id, question_text, userCountry, interestOne, 
                session_data, session_key
            )
        
        # Fetch consolidated JSON from S3
        json_response = requests.get(item["json_url"], timeout=10)
        json_response.raise_for_status()
        json_data = json_response.json()
        
        # Check interaction history
        interaction_history = session_data["semanticKeyInteractionHistory"].get(semantic_key, {})
        interaction_count = interaction_history.get("interactionCount", 0)
        last_semantic_key = session_data.get("lastSemanticKeyOverall")
        
        print(f"📊 Interaction count for {semantic_key}: {interaction_count}")
        print(f" Last semantic key: {last_semantic_key}")
        
        if interaction_count == 0 or semantic_key != last_semantic_key:
            # First interaction with this semantic key
            print("🆕 First interaction with this semantic key")
            return await handle_first_interaction(
                json_data, question_text, userCountry, interestOne,
                session_data, session_key, semantic_key
            )
        else:
            # Follow-up interaction - try specific answers
            print("🔄 Follow-up interaction")
            return await handle_follow_up_interaction(
                json_data, question_text, userCountry, interestOne,
                session_data, session_key, semantic_key
            )
            
    except Exception as e:
        print(f"Error in handle_successful_semantic_mapping: {e}")
        return await handle_llm_fallback(
            landmark_id, question_text, userCountry, interestOne, 
            session_data, session_key
        )

async def handle_first_interaction(
    json_data: dict, question_text: str, userCountry: str, interestOne: str,
    session_data: dict, session_key: str, semantic_key: str
):
    """Handle first interaction with a semantic key - return full response"""
    try:
        # Find the best matching response from the responses array
        responses = json_data.get("responses", [])
        best_response = find_best_response(responses, userCountry, interestOne)
        
        if best_response:
            answer = best_response
            source = "database_full"
            
            # Update session
            update_session_data(session_data, semantic_key, question_text, answer, source)
            session_store[session_key] = session_data
            
            return {
                "status": "success",
                "message": "Retrieved full response from database",
                "data": {
                    "answer": answer,
                    "source": source
                },
                "debug": {
                    "semanticKeyUsed": semantic_key,
                    "interactionCount": session_data["semanticKeyInteractionHistory"].get(semantic_key, {}).get("interactionCount", 0),
                    "retrievalPath": "full_response_initial"
                }
            }
        else:
            # No matching response found, fallback to LLM
            return await handle_llm_fallback(
                json_data.get("landmark", ""), question_text, userCountry, interestOne, 
                session_data, session_key
            )
            
    except Exception as e:
        print(f"Error in handle_first_interaction: {e}")
        return await handle_llm_fallback(
            json_data.get("landmark", ""), question_text, userCountry, interestOne, 
            session_data, session_key
        )

async def handle_follow_up_interaction(
    json_data: dict, question_text: str, userCountry: str, interestOne: str,
    session_data: dict, session_key: str, semantic_key: str
):
    """Handle follow-up interactions with specific answer lookup"""
    try:
        # 1. Try direct lookup in specific_Youtubes
        specific_youtubes = json_data.get("specific_Youtubes", {})
        normalized_question = question_text.lower().strip()
        
        print(f"🔍 Looking for specific answer in {len(specific_youtubes)} YouTube-style responses")
        
        for key, value in specific_youtubes.items():
            if any(word in normalized_question for word in key.lower().split()):
                print(f"✅ Found specific answer: {key}")
                answer = value
                source = "database_qa"
                
                # Update session
                update_session_data(session_data, semantic_key, question_text, answer, source)
                session_store[session_key] = session_data
                
                return {
                    "status": "success",
                    "message": "Retrieved specific answer from database",
                    "data": {
                        "answer": answer,
                        "source": source
                    },
                    "debug": {
                        "semanticKeyUsed": semantic_key,
                        "interactionCount": session_data["semanticKeyInteractionHistory"].get(semantic_key, {}).get("interactionCount", 0),
                        "retrievalPath": "qa_match"
                    }
                }
        
        # 2. Try extracted_details lookup
        extracted_details = json_data.get("extracted_details", {})
        print(f"🔍 Looking for extracted detail in {len(extracted_details)} details")
        
        # Simple keyword matching for extracted details
        for key, value in extracted_details.items():
            if any(word in normalized_question for word in key.lower().split()):
                print(f"✅ Found extracted detail: {key}")
                answer = value
                source = "database_extracted"
                
                # Update session
                update_session_data(session_data, semantic_key, question_text, answer, source)
                session_store[session_key] = session_data
                
                return {
                    "status": "success",
                    "message": "Retrieved extracted detail from database",
                    "data": {
                        "answer": answer,
                        "source": source
                    },
                    "debug": {
                        "semanticKeyUsed": semantic_key,
                        "interactionCount": session_data["semanticKeyInteractionHistory"].get(semantic_key, {}).get("interactionCount", 0),
                        "retrievalPath": "extracted_details_lookup"
                    }
                }
        
        # 3. LLM fallback for specific detail
        print(" No specific answer found, using LLM fallback")
        return await handle_llm_specific_detail(
            json_data, question_text, userCountry, interestOne,
            session_data, session_key, semantic_key
        )
        
    except Exception as e:
        print(f"Error in handle_follow_up_interaction: {e}")
        return await handle_llm_fallback(
            json_data.get("landmark", ""), question_text, userCountry, interestOne, 
            session_data, session_key
        )

async def handle_llm_specific_detail(
    json_data: dict, question_text: str, userCountry: str, interestOne: str,
    session_data: dict, session_key: str, semantic_key: str
):
    """Handle LLM fallback for specific detail requests"""
    try:
        print("🤖 Using LLM for specific detail generation")
        
        # Get landmark type for context
        landmark_type = get_landmark_type(json_data.get("landmark", ""))
        
        # Generate specific detail using LLM
        answer = await llm_service.generate_response(
            question=question_text,
            landmark_id=json_data.get("landmark", "").replace(" ", "_"),
            landmark_type=landmark_type,
            user_country=userCountry,
            interest=interestOne
        )
        
        source = "llm_generated_detail"
        
        # Update session
        update_session_data(session_data, semantic_key, question_text, answer, source)
        session_store[session_key] = session_data
        
        return {
            "status": "success",
            "message": "Generated specific detail via LLM",
            "data": {
                "answer": answer,
                "source": source
            },
            "debug": {
                "semanticKeyUsed": semantic_key,
                "interactionCount": session_data["semanticKeyInteractionHistory"].get(semantic_key, {}).get("interactionCount", 0),
                "retrievalPath": "llm_specific_detail",
                "llmPromptTokens": 0,  # TODO: Add actual token counting
                "llmCompletionTokens": 0
            }
        }
        
    except Exception as e:
        print(f"Error in handle_llm_specific_detail: {e}")
        return await handle_llm_fallback(
            json_data.get("landmark", ""), question_text, userCountry, interestOne, 
            session_data, session_key
        )

async def handle_llm_fallback(
    landmark_id: str, question_text: str, userCountry: str, interestOne: str,
    session_data: dict, session_key: str
):
    """Handle LLM fallback for new semantic keys"""
    try:
        print("🤖 Using LLM for new semantic key generation")
        
        # Get landmark type for context
        landmark_type = get_landmark_type(landmark_id)
        
        # Generate new response using LLM
        answer = await llm_service.generate_response(
            question=question_text,
            landmark_id=landmark_id,
            landmark_type=landmark_type,
            user_country=userCountry,
            interest=interestOne
        )
        
        source = "llm_generated_new"
        
        # Update session
        update_session_data(session_data, "unknown", question_text, answer, source)
        session_store[session_key] = session_data
        
        return {
            "status": "success",
            "message": "Generated new response via LLM",
            "data": {
                "answer": answer,
                "source": source
            },
            "debug": {
                "semanticKeyUsed": "unknown",
                "interactionCount": 0,
                "retrievalPath": "llm_new_semantic_key",
                "llmPromptTokens": 0,  # TODO: Add actual token counting
                "llmCompletionTokens": 0
            }
        }
        
    except Exception as e:
        print(f"Error in handle_llm_fallback: {e}")
        raise HTTPException(status_code=500, detail=f"LLM fallback failed: {str(e)}")

def get_landmark_type(landmark_id: str) -> str:
    """Get landmark type from landmarks table or default"""
    try:
        # Query landmarks table to get type
        landmarks_table = dynamodb.Table("Landmarks")
        response = landmarks_table.get_item(Key={"landmark_id": landmark_id})
        item = response.get("Item")
        return item.get("type", "unknown") if item else "unknown"
    except Exception as e:
        print(f"Error getting landmark type: {e}")
        return "unknown"

def find_best_response(responses: list, userCountry: str, interestOne: str) -> str:
    """Find the best matching response from the responses array"""
    if not responses:
        return None
    
    # Try exact match: country + category
    for resp in responses:
        if (resp.get("user_country") == userCountry and 
            resp.get("mapped_category") == interestOne):
            return resp["response"]
    
    # Fallback: try just country match
    for resp in responses:
        if resp.get("user_country") == userCountry:
            return resp["response"]
    
    # Final fallback: use first available response
    return responses[0]["response"] if responses else None

def update_session_data(session_data: dict, semantic_key: str, question_text: str, answer: str, source: str):
    """Update session data with current interaction"""
    current_time = time.time()
    
    # Initialize session if needed
    if session_data.get("sessionStartTime") is None:
        session_data["sessionStartTime"] = current_time
    
    # Update interaction history for this semantic key
    if semantic_key not in session_data["semanticKeyInteractionHistory"]:
        session_data["semanticKeyInteractionHistory"][semantic_key] = {
            "lastAccessTime": current_time,
            "interactionCount": 0,
            "lastQuestion": None,
            "lastAnswerType": None
        }
    
    history = session_data["semanticKeyInteractionHistory"][semantic_key]
    history["lastAccessTime"] = current_time
    history["interactionCount"] += 1
    history["lastQuestion"] = question_text
    history["lastAnswerType"] = source
    
    # Update overall session data
    session_data["lastActivityTime"] = current_time
    session_data["lastQuestionOverall"] = question_text
    session_data["lastAnswerOverall"] = answer
    session_data["lastSemanticKeyOverall"] = semantic_key
    
    print(f"📊 Updated session data for {semantic_key}, interaction count: {history['interactionCount']}") 