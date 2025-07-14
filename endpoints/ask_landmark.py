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
    Handle landmark questions - always try specific answers first, then LLM fallback
    """
    try:
        print(f"🎯 Processing ask-landmark request: {landmark}, {userId}")
        
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
        
        # 3. Semantic key mapping
        semantic_key, confidence = semantic_matching_service.get_landmark_specific_semantic_key(
            question_text, landmark_id
        )
        
        print(f"🔍 Semantic mapping result: {semantic_key} (confidence: {confidence})")
        
        if semantic_key and confidence > 0.4:  # High confidence threshold
            # 4. Handle successful semantic key mapping
            return await handle_semantic_mapping(
                landmark_id, semantic_key, question_text, userCountry, interestOne
            )
        else:
            # 5. Handle unsuccessful semantic key mapping (LLM fallback)
            return await handle_llm_fallback(
                landmark_id, question_text, userCountry, interestOne
            )
            
    except Exception as e:
        print(" ERROR in /ask-landmark:", e)
        raise HTTPException(status_code=500, detail=f"Failed to process question: {str(e)}")

async def handle_semantic_mapping(
    landmark_id: str, semantic_key: str, question_text: str, 
    userCountry: str, interestOne: str
):
    """Handle semantic key mapping - always try specific answers first"""
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
                landmark_id, question_text, userCountry, interestOne
            )
        
        # ✅ FIX: Read directly from S3 instead of CloudFront to avoid caching issues
        original_json_url = item["json_url"]
        print(f" Fetching JSON from S3: {original_json_url}")
        
        # Extract S3 key from CloudFront URL
        url_path = original_json_url.split('.net/')[-1]
        s3_key = url_path
        
        # Read directly from S3
        try:
            s3_response = s3_client.get_object(Bucket=S3_BUCKET, Key=s3_key)
            json_data = json.loads(s3_response['Body'].read().decode('utf-8'))
            print(f"✅ Read directly from S3: {s3_key}")
        except Exception as e:
            print(f"⚠️ Failed to read from S3, falling back to CloudFront: {e}")
            # Fallback to CloudFront
            json_response = requests.get(original_json_url, timeout=10)
            json_response.raise_for_status()
            json_data = json_response.json()
        
        # Debug: Print the actual JSON content being read
        print(f"🔍 JSON data keys: {list(json_data.keys())}")
        print(f" JSON data content: {json.dumps(json_data, indent=2)[:500]}...")
        
        # ALWAYS try specific answers first
        print("🔍 Always trying specific answers first")
        return await try_specific_answers(
            json_data, question_text, userCountry, interestOne, semantic_key, landmark_id, original_json_url
        )
            
    except Exception as e:
        print(f"Error in handle_semantic_mapping: {e}")
        return await handle_llm_fallback(
            landmark_id, question_text, userCountry, interestOne
        )

async def try_specific_answers(
    json_data: dict, question_text: str, userCountry: str, interestOne: str,
    semantic_key: str, landmark_id: str, original_json_url: str
):
    """Try to find specific answers in the JSON data"""
    try:
        specific_youtubes = json_data.get("specific_Youtubes", {})
        extracted_details = json_data.get("extracted_details", {})
        normalized_question = question_text.lower().strip()
        
        print(f"🔍 Looking for specific answer in {len(specific_youtubes)} YouTube-style responses")
        print(f"🔍 Looking for extracted details in {len(extracted_details)} details")
        
        # Debug: Print the actual keys we're searching
        print(f"🔍 Specific YouTube keys: {list(specific_youtubes.keys())}")
        print(f"🔍 Extracted detail keys: {list(extracted_details.keys())}")
        
        # 1. Try exact keyword matching in specific_Youtubes
        for key, value in specific_youtubes.items():
            print(f"🔍 Comparing: '{normalized_question}' with stored key: '{key}'")
            if normalized_question == key.lower():
                # Exact match
                print(f"✅ Found exact keyword match: {key}")
                return {
                    "status": "success",
                    "message": "Retrieved specific answer from database",
                    "data": {
                        "answer": value,
                        "source": "database_qa"
                    },
                    "debug": {
                        "semanticKeyUsed": semantic_key,
                        "retrievalPath": "exact_qa_match"
                    }
                }
            elif any(word in key.lower() for word in normalized_question.split()):
                # Contains match
                print(f"✅ Found contains keyword match: {key}")
                return {
                    "status": "success",
                    "message": "Retrieved specific answer from database",
                    "data": {
                        "answer": value,
                        "source": "database_qa"
                    },
                    "debug": {
                        "semanticKeyUsed": semantic_key,
                        "retrievalPath": "contains_qa_match"
                    }
                }
        
        # 2. Try semantic similarity matching for Q&A pairs
        similar_qa, similarity = await find_similar_qa_pair(question_text, specific_youtubes)
        if similar_qa and similarity > 0.6:
            qa_question, qa_answer = similar_qa
            print(f"✅ Found semantically similar Q&A: {qa_question} (similarity: {similarity})")
            
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
        for key, value in extracted_details.items():
            if any(word in normalized_question for word in key.lower().split()):
                print(f"✅ Found extracted detail: {key}")
                return {
                    "status": "success",
                    "message": "Retrieved extracted detail from database",
                    "data": {
                        "answer": value,
                        "source": "database_extracted"
                    },
                    "debug": {
                        "semanticKeyUsed": semantic_key,
                        "retrievalPath": "extracted_details_lookup"
                    }
                }
        
        # 4. If no specific answer found, use LLM with fact extraction
        print(" No specific answer found, using LLM fallback with fact extraction")
        return await handle_llm_with_facts(
            json_data, question_text, userCountry, interestOne, semantic_key, landmark_id, original_json_url
        )
        
    except Exception as e:
        print(f"Error in try_specific_answers: {e}")
        return await handle_llm_fallback(
            landmark_id, question_text, userCountry, interestOne
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

async def handle_llm_with_facts(
    json_data: dict, question_text: str, userCountry: str, interestOne: str,
    semantic_key: str, landmark_id: str, original_json_url: str
):
    """Handle LLM fallback with fact extraction"""
    try:
        print("🤖 Using LLM for specific detail generation with fact extraction")
        
        # Get landmark type for context
        landmark_type = get_landmark_type(json_data.get("landmark", ""))
        
        # Generate specific detail using LLM
        answer = await llm_service.generate_response(
            question=question_text,
            landmark_id=landmark_id,
            landmark_type=landmark_type,
            user_country=userCountry,
            interest=interestOne
        )
        
        source = "llm_generated_detail"
        
        # Extract facts from the answer
        extracted_facts = await extract_facts_from_response(question_text, answer)
        
        # Update JSON file with new Q&A pair AND extracted facts
        await update_json_with_qa_and_facts(
            json_data, question_text, answer, extracted_facts, 
            semantic_key, landmark_id, original_json_url
        )
        
        return {
            "status": "success",
            "message": "Generated new answer using LLM",
            "data": {
                "answer": answer,
                "source": source
            },
            "debug": {
                "semanticKeyUsed": semantic_key,
                "retrievalPath": "llm_generated",
                "factsExtracted": len(extracted_facts)
            }
        }
        
    except Exception as e:
        print(f"Error in handle_llm_with_facts: {e}")
        return await handle_llm_fallback(
            landmark_id, question_text, userCountry, interestOne
        )

async def handle_llm_fallback(
    landmark_id: str, question_text: str, userCountry: str, interestOne: str
):
    """Handle LLM fallback when semantic mapping fails"""
    try:
        print("�� Using LLM fallback for general question")
        
        # Get landmark type for context
        landmark_type = get_landmark_type(landmark_id)
        
        # Generate response using LLM
        answer = await llm_service.generate_response(
            question=question_text,
            landmark_id=landmark_id,
            landmark_type=landmark_type,
            user_country=userCountry,
            interest=interestOne
        )
        
        return {
            "status": "success",
            "message": "Generated answer using LLM fallback",
            "data": {
                "answer": answer,
                "source": "llm_fallback"
            },
            "debug": {
                "semanticKeyUsed": None,
                "retrievalPath": "llm_fallback"
            }
        }
        
    except Exception as e:
        print(f"Error in handle_llm_fallback: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate response: {str(e)}")

async def extract_facts_from_response(question: str, answer: str) -> dict:
    """Extract facts from LLM response"""
    try:
        # Use LLM to extract facts from the answer
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
            # Extract JSON from the response
            start_idx = facts_response.find('{')
            end_idx = facts_response.rfind('}') + 1
            if start_idx != -1 and end_idx > start_idx:
                json_str = facts_response[start_idx:end_idx]
                extracted_facts = json.loads(json_str)
            else:
                # Fallback: create simple fact
                extracted_facts = {"general_info": answer[:100] + "..."}
        except json.JSONDecodeError:
            # Fallback: create simple fact
            extracted_facts = {"general_info": answer[:100] + "..."}
        
        return extracted_facts
        
    except Exception as e:
        print(f"Error extracting facts: {e}")
        return {"general_info": answer[:100] + "..."}

async def update_json_with_qa_and_facts(
    json_data: dict, question_text: str, answer: str, extracted_facts: dict, 
    semantic_key: str, landmark_id: str, original_json_url: str
):
    """Update JSON file with new Q&A pair and extracted facts"""
    try:
        # Add new Q&A pair to specific_Youtubes
        if "specific_Youtubes" not in json_data:
            json_data["specific_Youtubes"] = {}
        
        json_data["specific_Youtubes"][question_text] = answer
        
        # Merge extracted facts with existing ones
        if "extracted_details" not in json_data:
            json_data["extracted_details"] = {}
        
        json_data["extracted_details"].update(extracted_facts)
        
        # Update timestamp
        json_data["last_updated_utc"] = datetime.utcnow().isoformat() + "Z"
        
        # ✅ FIX: Extract S3 key from the original CloudFront URL
        # Parse the URL to get the S3 key
        # Example: https://dmaq21q34jfdq.cloudfront.net/semantic_responses/saint_anne_byzantine_catholic_church_architecture.style.json
        # We need to extract: semantic_responses/saint_anne_byzantine_catholic_church_architecture.style.json
        
        # Remove the CloudFront domain and get the path
        url_path = original_json_url.split('.net/')[-1]
        s3_key = url_path
        
        # Convert to JSON string
        json_content = json.dumps(json_data, indent=2)
        
        # Upload to S3 using the same key as the original URL
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=json_content,
            ContentType="application/json"
        )
        
        print(f"✅ Updated JSON file: {s3_key}")
        print(f"✅ Writing to same location as original URL: {original_json_url}")
        print(f"✅ Added Q&A pair: '{question_text}'")
        print(f"✅ Added {len(extracted_facts)} extracted facts")
        
    except Exception as e:
        print(f"Error updating JSON: {e}")

def get_landmark_type(landmark_id: str) -> str:
    """Get landmark type for context"""
    # Simple mapping - can be enhanced
    if "church" in landmark_id.lower():
        return "religious"
    elif "park" in landmark_id.lower():
        return "recreational"
    elif "museum" in landmark_id.lower():
        return "cultural"
    else:
        return "general" 