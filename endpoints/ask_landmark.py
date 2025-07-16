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
# Remove this line: from services.dynamic_semantic_service import dynamic_semantic_service

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

# === Add simple semantic key creation logic ===
def create_semantic_key_from_question(question_text: str, landmark_id: str) -> str:
    """Create a semantic key based on the question content"""
    question_lower = question_text.lower()
    
    # Simple keyword-based mapping
    if any(word in question_lower for word in ["jog", "run", "exercise", "workout", "fitness"]):
        return "recreation.nearby"
    elif any(word in question_lower for word in ["eat", "food", "restaurant", "dining", "lunch", "dinner"]):
        return "dining.nearby"
    elif any(word in question_lower for word in ["park", "parking", "car", "drive"]):
        return "access.parking"
    elif any(word in question_lower for word in ["bus", "transport", "transit", "subway", "train"]):
        return "access.transport"
    elif any(word in question_lower for word in ["photo", "picture", "instagram", "selfie"]):
        return "culture.photography"
    elif any(word in question_lower for word in ["history", "historical", "past", "origin"]):
        return "origin.general"
    elif any(word in question_lower for word in ["name", "called", "title"]):
        return "origin.name"
    elif any(word in question_lower for word in ["symbol", "meaning", "significance"]):
        return "culture.symbolism"
    elif any(word in question_lower for word in ["story", "legend", "myth", "tale"]):
        return "myths.legends"
    else:
        # Default to a general category based on landmark type
        landmark_type = get_landmark_type(landmark_id)
        return f"{landmark_type}.general"

async def update_semantic_config(landmark_id: str, semantic_key: str, question_text: str) -> bool:
    """Update semantic_config.json in S3 with new semantic key"""
    try:
        print(f"📝 Updating semantic_config.json in S3 with new key: {semantic_key}")
        
        # 1. Get landmark type
        landmark_type = get_landmark_type(landmark_id)
        print(f"📝 Landmark type: {landmark_type}")
        
        # 2. Read current semantic_config.json from S3
        s3_config_key = "config/semantic_config.json"
        try:
            s3_response = s3_client.get_object(Bucket=S3_BUCKET, Key=s3_config_key)
            config_data = json.loads(s3_response['Body'].read().decode('utf-8'))
            print(f"✅ Read semantic_config.json from S3: {s3_config_key}")
        except Exception as e:
            print(f"⚠️ Failed to read from S3, trying local file: {e}")
            try:
                with open("scripts/semantic_config.json", "r") as f:
                    config_data = json.load(f)
                print(f"✅ Read semantic_config.json from local file")
            except Exception as e2:
                print(f"❌ Failed to read semantic_config.json: {e2}")
                return False
        
        # 3. Add new semantic key to the appropriate landmark type
        if landmark_type not in config_data:
            config_data[landmark_type] = {}
        
        # 4. Use hybrid approach to create prompt template
        prompt_template = await get_smart_prompt_for_semantic_key(
            semantic_key, question_text, config_data
        )
        
        # 5. Add the new semantic key with its prompt
        config_data[landmark_type][semantic_key] = prompt_template
        
        print(f"✅ Added new semantic key '{semantic_key}' to '{landmark_type}' section")
        
        # 6. Upload updated config back to S3
        config_content = json.dumps(config_data, indent=2)
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=s3_config_key,
            Body=config_content,
            ContentType="application/json"
        )
        
        print(f"✅ Updated semantic_config.json in S3: {s3_config_key}")
        print(f"✅ Added prompt template for: {semantic_key}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error updating semantic config: {e}")
        return False

async def ask_landmark_question(
    landmark: str = Form(...),
    userCountry: str = Form("United States"),
    interestOne: str = Form("Nature"),
    userId: str = Form(...),
    audio_file: UploadFile = File(None),
    age: str = Form("25")  
):
    """
    Handle landmark questions - always try specific answers first, then LLM fallback
    """
    try:
        # Convert age to integer since form data is a string
        try:
            age_int = int(age) if age else 25
        except (ValueError, TypeError):
            age_int = 25 
        
        print(f"Processing ask-landmark request: {landmark}, {userId}, age: {age_int}")
        
        # 1. Pre-process inputs
        landmark_id = landmark.replace(" ", "_")
        
        # 2. Get question text (from text or audio)
        question_text = None
        if audio_file:
            audio_content = await audio_file.read()
            file_extension = audio_file.filename.split(".")[-1] if "." in audio_file.filename else "m4a"
            question_text = await audio_processing_service.audio_to_text(audio_content, file_extension)
            print(f" Audio converted to question: '{question_text}'")
        
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
            # 5. ✅ NEW: Try dynamic semantic key creation with age
            print("🔧 No semantic key found, attempting dynamic creation...")
            return await handle_dynamic_semantic_creation(
                landmark_id, question_text, userCountry, interestOne, age_int  # Pass the converted integer
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
                # Exact match only - remove the problematic contains logic
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
        
        # ✅ NEW: Get landmark info (city/country) from landmarks.json
        city, country = get_landmark_info(landmark_id)  # Remove async since it's now synchronous
        print(f" Landmark location: {city}, {country}")
        
        # Get landmark type for context
        landmark_type = get_landmark_type(landmark_id)
        print(f"🏛️ Landmark type: {landmark_type}")
        
        # ✅ NEW: Use semantic config prompt with city/country instead of generic LLM
        # Get the prompt template for this semantic key
        prompt_template = get_prompt_template(semantic_key)
        
        if prompt_template:
            print(f"📝 Using semantic config prompt template for: {semantic_key}")
            # Format the prompt with city/country
            prompt = prompt_template.format(
                city=city,
                country=country,
                landmark=landmark_id.replace("_", " "),
                age_group="young",  # Default for now
                userCountry=userCountry,
                mappedCategory=interestOne
            )
            print(f"🎯 Formatted prompt: {prompt[:200]}...")
            
            # Use the formatted prompt with LLM
            answer = await llm_service.generate_response_with_prompt_and_age(
                prompt=prompt,
                question=question_text,
                landmark_id=landmark_id,
                user_country=userCountry,
                interest=interestOne,
                age_group="young"
            )
        else:
            print(f"⚠️ No prompt template found for {semantic_key}, using generic LLM")
            # Fallback to generic LLM
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

async def handle_dynamic_semantic_creation(
    landmark_id: str, question_text: str, userCountry: str, interestOne: str, age: int
):
    """Handle dynamic semantic key creation when no existing key matches"""
    try:
        print(" Attempting dynamic semantic key creation...")
        
        # 1. Get age group using existing utility
        from utils.age_utils import AgeUtils
        age_group = AgeUtils.classify_age(age)
        print(f" User age: {age} -> Age group: {age_group}")
        
        # 2. Create new semantic key based on the question
        new_semantic_key = create_semantic_key_from_question(question_text, landmark_id)
        
        if not new_semantic_key:
            print("❌ Failed to create semantic key, using general LLM fallback")
            return await handle_llm_fallback(
                landmark_id, question_text, userCountry, interestOne
            )
        
        print(f"✅ Created new semantic key: {new_semantic_key}")
        
        # 3. Update semantic_config.json with new key and prompt
        success = await update_semantic_config(landmark_id, new_semantic_key, question_text)
        
        if not success:
            print("❌ Failed to update semantic config, using general LLM fallback")
            return await handle_llm_fallback(
                landmark_id, question_text, userCountry, interestOne
            )
        
        print(f"✅ Updated semantic_config.json with new key: {new_semantic_key}")
        
        # 4. Generate response using the new semantic key with age
        return await handle_new_semantic_key(
            landmark_id, new_semantic_key, question_text, userCountry, interestOne, age_group
        )
        
    except Exception as e:
        print(f"Error in handle_dynamic_semantic_creation: {e}")
        return await handle_llm_fallback(
            landmark_id, question_text, userCountry, interestOne
        )

async def handle_new_semantic_key(
    landmark_id: str, semantic_key: str, question_text: str, 
    userCountry: str, interestOne: str, age_group: str
):
    """Handle newly created semantic key - generate response and create JSON file"""
    try:
        print(f"🎯 Generating response for new semantic key: {semantic_key}")
        
        # ✅ NEW: Get landmark info (city/country) from landmarks table
        city, country = get_landmark_info(landmark_id)
        print(f" Landmark location: {city}, {country}")
        
        # 1. Get the prompt for this new semantic key
        prompt_template = get_prompt_template(semantic_key)  # Use existing function
        
        if not prompt_template:
            print("❌ Failed to get prompt for new semantic key")
            return await handle_llm_fallback(
                landmark_id, question_text, userCountry, interestOne
            )
        
        # ✅ FIXED: Format the prompt with city/country
        prompt = prompt_template.format(
            city=city,                    # ✅ Add city
            country=country,              # ✅ Add country
            landmark=landmark_id.replace("_", " "),
            age_group=age_group,
            userCountry=userCountry,
            mappedCategory=interestOne
        )
        
        # 3. Generate response using LLM with the new prompt
        answer = await llm_service.generate_response_with_prompt_and_age(
            prompt=prompt,
            question=question_text,
            landmark_id=landmark_id,
            user_country=userCountry,
            interest=interestOne,
            age_group=age_group
        )
        
        # 4. Extract facts from the response
        extracted_facts = await extract_facts_from_response(question_text, answer)
        
        # 5. Create new JSON file for this semantic key (following batch script pattern)
        json_data = {
            "landmark": landmark_id.replace("_", " "),
            "semantic_key": semantic_key,
            "responses": [
                {
                    "user_country": userCountry,
                    "user_age": age_group,
                    "mapped_category": interestOne,
                    "response": answer
                }
            ],
            "extracted_details": extracted_facts,
            "specific_Youtubes": {
                question_text: answer  # Add the current Q&A pair
            },
            "last_updated_utc": datetime.utcnow().isoformat() + "Z"
        }
        
        # 6. Upload to S3
        s3_key = f"semantic_responses/{landmark_id.lower()}_{semantic_key}.json"
        
        json_content = json.dumps(json_data, indent=2)
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=json_content,
            ContentType="application/json"
        )
        
        # 7. Update DynamoDB to point to the new JSON file
        json_url = f"{S3_URL_BASE}/{s3_key}"
        
        semantic_table.put_item(Item={
            "landmark_id": landmark_id,
            "semantic_key": semantic_key,
            "json_url": json_url,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "is_dynamic": True  # Flag to indicate this was created dynamically
        })
        
        print(f"✅ Created new JSON file: {s3_key}")
        print(f"✅ Updated DynamoDB with new semantic key: {semantic_key}")
        print(f"✅ Added Q&A pair: '{question_text}'")
        print(f"✅ Added {len(extracted_facts)} extracted facts")
        print(f"⚠️ NOTE: Run batch script later to populate all age groups and countries for this semantic key")
        
        # 8. Return the response
        return {
            "status": "success",
            "message": "Generated response using new semantic key",
            "data": {
                "answer": answer,
                "source": "dynamic_semantic_generated"
            },
            "debug": {
                "semanticKeyUsed": semantic_key,
                "retrievalPath": "dynamic_semantic_creation",
                "factsExtracted": len(extracted_facts),
                "newJsonFile": s3_key,
                "ageGroup": age_group,
                "needsBatchUpdate": True  # Flag to run batch script later
            }
        }
        
    except Exception as e:
        print(f"Error in handle_new_semantic_key: {e}")
        return await handle_llm_fallback(
            landmark_id, question_text, userCountry, interestOne
        )

def get_landmark_type(landmark_id: str) -> str:
    """Get landmark type from landmarks.json"""
    try:
        # Read from landmarks.json to get the actual type
        with open("scripts/landmarks.json", "r") as f:
            landmarks = json.load(f)
        
        # Find the landmark by name
        landmark_name = landmark_id.replace("_", " ")
        for landmark in landmarks:
            if landmark["name"] == landmark_name:
                print(f"✅ Found landmark type: {landmark['type']} for {landmark_name}")
                return landmark["type"]  # This will return "religious" for Saint Anne
        
        print(f"⚠️ Landmark '{landmark_name}' not found in landmarks.json")
        return "general"
    except Exception as e:
        print(f"⚠️ Error reading landmarks.json: {e}")
        return "general"

def get_landmark_info(landmark_id: str) -> tuple:
    """Get landmark city and country from landmarks.json"""
    try:
        # Read from landmarks.json to get city/country
        with open("scripts/landmarks.json", "r") as f:
            landmarks = json.load(f)
        
        # Find the landmark by name
        landmark_name = landmark_id.replace("_", " ")
        for landmark in landmarks:
            if landmark["name"] == landmark_name:
                city = landmark.get("city", "San Luis Obispo")
                country = landmark.get("country", "United States")
                print(f"✅ Found landmark location: {city}, {country} for {landmark_name}")
                return city, country
        
        print(f"⚠️ Landmark '{landmark_name}' not found in landmarks.json")
        return "San Luis Obispo", "United States"
    except Exception as e:
        print(f"⚠️ Error reading landmarks.json: {e}")
        return "San Luis Obispo", "United States"

async def get_smart_prompt_for_semantic_key(semantic_key: str, question_text: str, existing_config: dict) -> str:
    """Smart prompt generation using hybrid approach: pattern matching → template → LLM fallback"""
    
    print(f"🧠 Generating smart prompt for semantic key: {semantic_key}")
    
    # 1. Try pattern matching first (fastest)
    pattern_prompt = learn_prompt_from_existing(semantic_key, existing_config)
    if pattern_prompt and "helpful information" not in pattern_prompt:
        print(f"✅ Used pattern matching: {pattern_prompt[:100]}...")
        return pattern_prompt
    
    # 2. Try template system
    template_prompt = get_prompt_template(semantic_key)
    if template_prompt and "helpful information" not in template_prompt:
        print(f"✅ Used template system: {template_prompt[:100]}...")
        return template_prompt
    
    # 3. Use LLM generation as fallback (most flexible but slower)
    print(f"🤖 Using LLM generation for: {semantic_key}")
    return await generate_prompt_from_semantic_key(semantic_key, question_text, existing_config)

def learn_prompt_from_existing(semantic_key: str, existing_config: dict) -> str:
    """Learn prompt pattern from existing semantic keys"""
    
    # Find similar existing keys
    similar_keys = []
    for landmark_type, prompts in existing_config.items():
        for key in prompts.keys():
            # Check if keys share similar patterns
            if any(word in key for word in semantic_key.split('.')):
                similar_keys.append((key, prompts[key]))
    
    if similar_keys:
        # Use the most similar existing prompt as template
        most_similar_key, most_similar_prompt = similar_keys[0]
        
        # Replace the specific topic while keeping the structure
        new_prompt = most_similar_prompt.replace(
            most_similar_key.replace('.', ' '),
            semantic_key.replace('.', ' ')
        )
        
        return new_prompt
    
    return None

def get_prompt_template(semantic_key: str) -> str:
    """Get prompt template for semantic key - UPDATED with city/country"""
    prompts = {
        "recreation.nearby": "As Roamly, your personal AI tour guide in {city}, {country}, suggest nearby recreational spots around {landmark} for a {age_group} traveler from {userCountry} interested in {mappedCategory}. Focus on places within walking distance that offer good exercise opportunities.",
        "dining.nearby": "As Roamly, your personal AI tour guide in {city}, {country}, recommend nearby dining options around {landmark} for a {age_group} traveler from {userCountry} interested in {mappedCategory}. Suggest local favorites and convenient spots.",
        "transportation.nearby": "As Roamly, your personal AI tour guide in {city}, {country}, provide transportation information around {landmark} for a {age_group} traveler from {userCountry} interested in {mappedCategory}. Include parking, public transit, and accessibility options.",
        "shopping.nearby": "As Roamly, your personal AI tour guide in {city}, {country}, suggest nearby shopping areas around {landmark} for a {age_group} traveler from {userCountry} interested in {mappedCategory}. Highlight local markets, boutiques, and souvenir shops.",
        "history.timeline": "As Roamly, your personal AI tour guide in {city}, {country}, share the historical timeline of {landmark} for a {age_group} traveler from {userCountry} interested in {mappedCategory}. Focus on key events and milestones in chronological order.",
        "architecture.details": "As Roamly, your personal AI tour guide in {city}, {country}, describe the architectural details of {landmark} for a {age_group} traveler from {userCountry} interested in {mappedCategory}. Highlight unique design elements and construction techniques.",
        "culture.traditions": "As Roamly, your personal AI tour guide in {city}, {country}, explain the cultural traditions associated with {landmark} for a {age_group} traveler from {userCountry} interested in {mappedCategory}. Share local customs and practices.",
        "events.current": "As Roamly, your personal AI tour guide in {city}, {country}, inform about current events and activities at {landmark} for a {age_group} traveler from {userCountry} interested in {mappedCategory}. Include upcoming celebrations and special occasions.",
        "accessibility.info": "As Roamly, your personal AI tour guide in {city}, {country}, provide accessibility information for {landmark} for a {age_group} traveler from {userCountry} interested in {mappedCategory}. Include wheelchair access, ramps, and special accommodations.",
        "photography.tips": "As Roamly, your personal AI tour guide in {city}, {country}, share photography tips for {landmark} for a {age_group} traveler from {userCountry} interested in {mappedCategory}. Suggest best angles, lighting, and unique perspectives."
    }
    return prompts.get(semantic_key, "As Roamly, your personal AI tour guide in {city}, {country}, provide helpful information about {landmark} for a {age_group} traveler from {userCountry} interested in {mappedCategory}.")

async def generate_prompt_from_semantic_key(semantic_key: str, question_text: str, existing_config: dict) -> str:
    """Use LLM to generate a prompt template based on semantic key and existing patterns"""
    
    # Get a few examples from existing config
    example_prompts = []
    for landmark_type, prompts in existing_config.items():
        for key, prompt in list(prompts.items())[:3]:  # Get 3 examples
            example_prompts.append(f"Key: {key}\nPrompt: {prompt}")
    
    examples_text = "\n\n".join(example_prompts)
    
    llm_prompt = f"""
    Based on these existing prompt templates, generate a new prompt for semantic key "{semantic_key}".
    
    The user asked: "{question_text}"
    
    Existing examples:
    {examples_text}
    
    Generate a prompt that follows the same style and format as the examples above.
    The prompt should be for a tour guide explaining {semantic_key.replace('.', ' ')}.
    Include placeholders for {{landmark}}, {{age_group}}, {{userCountry}}, and {{mappedCategory}}.
    
    New prompt:
    """
    
    # Use LLM to generate the prompt
    response = await llm_service.generate_response(
        question=llm_prompt,
        landmark_id="prompt_generation",
        landmark_type="system",
        user_country="system",
        interest="system"
    )
    
    return response.strip() 