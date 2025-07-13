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

# === Setup S3 ===
s3_client = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION", "us-east-2")
)
S3_BUCKET = os.getenv("S3_BUCKET_NAME")
S3_URL_BASE = os.getenv("S3_URL_BASE")

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
        
        # ✅ FIX: Create stable session key that doesn't change on server restart
        stable_session_key = f"{userId}:{landmark_id}"
        
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
        
        # 3. Session management with stable key
        session_data = get_or_initialize_session(stable_session_key, userId, sessionId, landmark_id)
        
        # 4. Semantic key mapping
        semantic_key, confidence = semantic_matching_service.get_landmark_specific_semantic_key(
            question_text, landmark_id
        )
        
        print(f"🔍 Semantic mapping result: {semantic_key} (confidence: {confidence})")
        
        if semantic_key and confidence > 0.4:  # High confidence threshold
            # 5. Handle successful semantic key mapping
            return await handle_successful_semantic_mapping(
                landmark_id, semantic_key, question_text, userCountry, 
                interestOne, session_data, stable_session_key
            )
        else:
            # 6. Handle unsuccessful semantic key mapping (LLM fallback DISABLED)
            return await handle_llm_fallback_disabled(
                landmark_id, question_text, userCountry, interestOne, 
                session_data, stable_session_key
            )
            
    except Exception as e:
        print(" ERROR in /ask-landmark:", e)
        raise HTTPException(status_code=500, detail=f"Failed to process question: {str(e)}")

def get_or_initialize_session(session_key: str, userId: str, sessionId: str, landmark_id: str) -> dict:
    """Get existing session or initialize new one (simplified)"""
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
    """Handle successful semantic key mapping with intelligent response selection"""
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
            return await handle_llm_fallback_disabled(
                landmark_id, question_text, userCountry, interestOne, 
                session_data, session_key
            )
        
        # Fetch consolidated JSON from S3
        json_response = requests.get(item["json_url"], timeout=10)
        json_response.raise_for_status()
        json_data = json_response.json()
        
        # ALWAYS try specific answers first, regardless of session state
        print("🔍 Always trying specific answers first")
        return await handle_subsequent_session(
            json_data, question_text, userCountry, interestOne,
            session_data, session_key, semantic_key
        )
            
    except Exception as e:
        print(f"Error in handle_successful_semantic_mapping: {e}")
        return await handle_llm_fallback_disabled(
            landmark_id, question_text, userCountry, interestOne, 
            session_data, session_key
        )



async def handle_subsequent_session(
    json_data: dict, question_text: str, userCountry: str, interestOne: str,
    session_data: dict, session_key: str, semantic_key: str
):
    """Handle subsequent sessions - always try specific answers first"""
    try:
        specific_youtubes = json_data.get("specific_Youtubes", {})
        extracted_details = json_data.get("extracted_details", {})
        normalized_question = question_text.lower().strip()
        
        print(f"🔍 Looking for specific answer in {len(specific_youtubes)} YouTube-style responses")
        
        # 1. Try exact keyword matching in specific_Youtubes
        for key, value in specific_youtubes.items():
            if any(word in normalized_question for word in key.lower().split()):
                print(f"✅ Found exact keyword match: {key}")
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
                        "retrievalPath": "exact_qa_match"
                    }
                }
        
        # 2. Try semantic similarity matching for Q&A pairs
        similar_qa, similarity = await find_similar_qa_pair(question_text, specific_youtubes)
        if similar_qa and similarity > 0.6:
            qa_question, qa_answer = similar_qa
            print(f"✅ Found semantically similar Q&A: {qa_question} (similarity: {similarity})")
            
            # Update session
            update_session_data(session_data, semantic_key, question_text, qa_answer, "database_qa_semantic_match")
            session_store[session_key] = session_data
            
            return {
                "status": "success",
                "message": "Retrieved similar answer from database",
                "data": {
                    "answer": qa_answer,
                    "source": "database_qa_semantic_match"
                },
                "debug": {
                    "semanticKeyUsed": semantic_key,
                    "similarQuestion": qa_question,
                    "similarity": similarity,
                    "retrievalPath": "semantic_qa_match"
                }
            }
        
        # 3. Try extracted_details lookup
        print(f"🔍 Looking for extracted detail in {len(extracted_details)} details")
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
                        "retrievalPath": "extracted_details_lookup"
                    }
                }
        
        # 4. If no specific answer found, use LLM with fact extraction
        print(" No specific answer found, using LLM fallback with fact extraction")
        return await handle_llm_specific_detail_with_facts(
            json_data, question_text, userCountry, interestOne,
            session_data, session_key, semantic_key
        )
        
    except Exception as e:
        print(f"Error in handle_subsequent_session: {e}")
        return await handle_llm_fallback_disabled(
            json_data.get("landmark", ""), question_text, userCountry, interestOne, 
            session_data, session_key
        )

async def find_similar_qa_pair(question_text: str, specific_youtubes: dict) -> tuple:
    """Find similar Q&A pair using semantic matching"""
    try:
        best_match = None
        best_similarity = 0
        
        for qa_question, qa_answer in specific_youtubes.items():
            # Use semantic matching to compare questions
            similarity = semantic_matching_service.calculate_similarity(
                question_text, qa_question
            )
            
            if similarity > best_similarity and similarity > 0.6:  # Threshold
                best_similarity = similarity
                best_match = (qa_question, qa_answer)
        
        return best_match, best_similarity
        
    except Exception as e:
        print(f"Error finding similar Q&A pair: {e}")
        return None, 0

async def handle_llm_specific_detail_with_facts(
    json_data: dict, question_text: str, userCountry: str, interestOne: str,
    session_data: dict, session_key: str, semantic_key: str
):
    """Handle LLM fallback for specific detail requests with fact extraction"""
    try:
        print("🤖 Using LLM for specific detail generation with fact extraction")
        
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
        
        # Extract facts from the answer
        extracted_facts = await extract_facts_from_response(question_text, answer)
        
        # Update JSON file with new Q&A pair AND extracted facts
        await update_json_with_qa_and_facts(
            json_data, question_text, answer, extracted_facts, semantic_key, 
            json_data.get("landmark", "").replace(" ", "_")
        )
        
        # Update session
        update_session_data(session_data, semantic_key, question_text, answer, source)
        session_store[session_key] = session_data
        
        return {
            "status": "success",
            "message": "Generated specific detail via LLM and updated database with facts",
            "data": {
                "answer": answer,
                "source": source
            },
            "debug": {
                "semanticKeyUsed": semantic_key,
                "interactionCount": session_data["semanticKeyInteractionHistory"].get(semantic_key, {}).get("interactionCount", 0),
                "retrievalPath": "llm_specific_detail_with_facts",
                "jsonUpdated": True,
                "factsExtracted": len(extracted_facts) if extracted_facts else 0
            }
        }
        
    except Exception as e:
        print(f"Error in handle_llm_specific_detail_with_facts: {e}")
        return await handle_llm_fallback_disabled(
            json_data.get("landmark", ""), question_text, userCountry, interestOne, 
            session_data, session_key
        )

async def extract_facts_from_response(question: str, answer: str) -> dict:
    """Extract specific facts from LLM response"""
    try:
        prompt = f"""
        From this answer: "{answer}"
        
        Extract specific factual details that could be useful for future questions.
        Return as JSON with keys like: year_built, architect, style, height, materials, etc.
        
        Example: {{"year_built": "1923", "architect": "John Smith", "style": "Byzantine"}}
        
        Only return the JSON, nothing else.
        """
        
        response = await llm_service.generate_response(
            question=prompt,
            landmark_id="fact_extraction",
            landmark_type="utility",
            user_country="United States",
            interest="Technology"
        )
        
        # Parse the JSON response
        try:
            facts = json.loads(response)
            print(f" Extracted facts: {facts}")
            return facts
        except:
            print(f"⚠️ Failed to parse extracted facts: {response}")
            return {}
            
    except Exception as e:
        print(f"Error extracting facts: {e}")
        return {}

async def update_json_with_qa_and_facts(
    json_data: dict, question_text: str, answer: str, extracted_facts: dict, 
    semantic_key: str, landmark_id: str
):
    """Update existing JSON file with new Q&A pair AND extracted facts"""
    try:
        # Add to specific_Youtubes
        normalized_question = question_text.lower().strip()
        json_data["specific_Youtubes"][normalized_question] = answer
        
        # Add extracted facts to extracted_details
        if extracted_facts:
            for key, value in extracted_facts.items():
                if key not in json_data["extracted_details"]:
                    json_data["extracted_details"][key] = value
        
        # Update timestamp
        json_data["last_updated_utc"] = datetime.utcnow().isoformat() + "Z"
        
        # Get the S3 URL from DynamoDB
        response = semantic_table.get_item(
            Key={
                "landmark_id": landmark_id,
                "semantic_key": semantic_key
            }
        )
        
        item = response.get("Item")
        if not item:
            print(f"⚠️ No DynamoDB item found for {landmark_id}:{semantic_key}")
            return
        
        # Extract S3 key from URL
        json_url = item["json_url"]
        s3_key = json_url.replace(S3_URL_BASE, "")
        
        # Upload updated JSON to S3
        local_path = f"/tmp/updated_{landmark_id}_{semantic_key}.json"
        with open(local_path, "w") as f:
            json.dump(json_data, f, indent=2)
        
        s3_client.upload_file(
            local_path,
            S3_BUCKET,
            s3_key,
            ExtraArgs={"ContentType": "application/json"}
        )
        
        # Clean up local file
        os.remove(local_path)
        
        print(f"✅ Updated JSON with new Q&A pair and {len(extracted_facts)} facts for {semantic_key}")
        
    except Exception as e:
        print(f"Error updating JSON with Q&A and facts: {e}")
        # Don't raise - this is not critical for the response

async def handle_llm_fallback_disabled(
    landmark_id: str, question_text: str, userCountry: str, interestOne: str,
    session_data: dict, session_key: str
):
    """Handle LLM fallback for new semantic keys - DISABLED for now"""
    try:
        print("🤖 LLM fallback for new semantic keys is currently disabled")
        
        # Update session with no data response
        update_session_data(session_data, "unknown", question_text, "No data available", "no_data_available")
        session_store[session_key] = session_data
        
        return {
            "status": "success",
            "message": "No data available for this question. Please try asking something else.",
            "data": {
                "answer": "I don't have specific information about that. Please try asking about visiting hours, history, architecture, or general information about this landmark.",
                "source": "no_data_available"
            },
            "debug": {
                "semanticKeyUsed": "unknown",
                "interactionCount": 0,
                "retrievalPath": "no_semantic_key_found",
                "llmFallbackDisabled": True
            }
        }
        
    except Exception as e:
        print(f"Error in handle_llm_fallback_disabled: {e}")
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