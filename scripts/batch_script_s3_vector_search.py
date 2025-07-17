#!/usr/bin/env python3
"""
Batch script for populating S3 Vector Search indexes.
Replaces the old JSON-based approach with vector-based storage for better performance.
"""

import os
import sys
import json
import asyncio
from datetime import datetime
from dotenv import load_dotenv
import boto3
import openai

# Add the parent directory to Python path to import services
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from services.advanced_s3_vector_service import advanced_s3_vector_service

# Load environment variables
load_dotenv()

# Setup OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Setup S3
s3_client = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION", "us-east-2")
)
S3_BUCKET = os.getenv("S3_BUCKET_NAME")

# Load configuration files from S3
def load_config_files():
    """Load all configuration files from S3."""
    configs = {}
    
    try:
        # Use the existing S3 config reader
        from utils.s3_config_reader import get_landmarks_from_s3, get_semantic_config_from_s3
        
        print("📥 Loading configuration from S3...")
        
        # Load landmarks and semantic config
        configs["landmarks.json"] = get_landmarks_from_s3()
        configs["semantic_config.json"] = get_semantic_config_from_s3()
        
        # Load other config files from S3
        config_files = [
            ("config/countries.json", "countries.json"),
            ("config/interests.json", "interests.json"),
            ("config/languages.json", "languages.json")
        ]
        
        for s3_key, local_name in config_files:
            try:
                response = s3_client.get_object(Bucket=S3_BUCKET, Key=s3_key)
                content = response['Body'].read().decode('utf-8')
                configs[local_name] = json.loads(content)
                print(f"✅ Loaded {s3_key} from S3")
            except Exception as e:
                print(f"❌ Error loading {s3_key} from S3: {e}")
                # Provide fallback defaults
                if local_name == "countries.json":
                    configs[local_name] = {"countries": ["United States", "India", "Canada"]}
                elif local_name == "interests.json":
                    configs[local_name] = {"interests": ["Nature", "History", "Food", "Technology"]}
                elif local_name == "languages.json":
                    configs[local_name] = {"languages": ["English", "Spanish", "Hindi"]}
        
        print("✅ Configuration loaded from S3")
        
    except Exception as e:
        print(f"❌ Error loading from S3: {e}")
        # Fallback to empty configs
        configs = {
            "landmarks.json": [],
            "semantic_config.json": {},
            "countries.json": {"countries": ["United States", "India", "Canada"]},
            "interests.json": {"interests": ["Nature", "History", "Food", "Technology"]},
            "languages.json": {"languages": ["English", "Spanish", "Hindi"]}
        }
    
    return configs

def get_relevant_semantic_keys(landmark_type: str, semantic_config: dict) -> list:
    """Get relevant semantic keys for a landmark type."""
    return list(semantic_config.get(landmark_type, {}).keys())

def get_prompt_template(semantic_key: str, semantic_config: dict) -> str:
    """Get prompt template for a semantic key."""
    for landmark_type, keys in semantic_config.items():
        if semantic_key in keys:
            return keys[semantic_key]
    return None

async def generate_landmark_response(landmark: dict, semantic_key: str, 
                                  user_country: str, interest: str, age: int,
                                  semantic_config: dict) -> str:
    """Generate a personalized response for a landmark and semantic key."""
    try:
        # Get prompt template
        prompt_template = get_prompt_template(semantic_key, semantic_config)
        if not prompt_template:
            print(f"⚠️ No prompt template found for {semantic_key}")
            return None
        
        # Format the prompt with landmark info
        age_group = "young" if age < 30 else "middleage" if age <= 60 else "old"
        
        prompt = prompt_template.format(
            city=landmark.get("city", "a city"),
            country=landmark.get("country", "a country"),
            landmark=landmark["name"],
            age_group=age_group,
            userCountry=user_country,
            mappedCategory=interest
        )
        
        # Generate response using OpenAI
        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        completion = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a friendly and knowledgeable travel guide."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=500
        )
        
        response = completion.choices[0].message.content.strip()
        print(f"✅ Generated response for {landmark['name']} - {semantic_key} ({user_country}/{interest}/{age_group})")
        
        return response
        
    except Exception as e:
        print(f"❌ Error generating response for {landmark['name']} - {semantic_key}: {e}")
        return None

async def populate_landmark_responses(landmark: dict, semantic_keys: list, 
                                   countries: list, interests: list, ages: list,
                                   semantic_config: dict):
    """Populate responses for a single landmark across all combinations."""
    print(f"\n🏛️ Processing landmark: {landmark['name']}")
    print(f"📍 Location: {landmark.get('city', 'Unknown')}, {landmark.get('country', 'Unknown')}")
    print(f"🔑 Semantic keys: {semantic_keys}")
    
    responses_added = 0
    
    for semantic_key in semantic_keys:
        print(f"\n📝 Processing semantic key: {semantic_key}")
        
        for country in countries:
            for interest in interests:
                for age in ages:
                    try:
                        # Generate personalized response
                        response = await generate_landmark_response(
                            landmark=landmark,
                            semantic_key=semantic_key,
                            user_country=country,
                            interest=interest,
                            age=age,
                            semantic_config=semantic_config
                        )
                        
                        if response:
                            # Add to S3 Vector Search as landmark response
                            advanced_s3_vector_service.add_landmark_response(
                                landmark_id=landmark["name"].replace(" ", "_"),
                                semantic_key=semantic_key,
                                response=response,
                                user_country=country,
                                interest=interest,
                                age=age,
                                metadata={
                                    "batch_generated": True,
                                    "generated_at": datetime.utcnow().isoformat(),
                                    "landmark_type": landmark.get("type", "tourist_attraction")
                                }
                            )
                            
                            responses_added += 1
                            
                            # Small delay to avoid rate limits
                            await asyncio.sleep(0.1)
                        
                    except Exception as e:
                        print(f"❌ Error processing {landmark['name']} - {semantic_key} ({country}/{interest}/{age}): {e}")
                        continue
    
    print(f"✅ Added {responses_added} responses for {landmark['name']}")
    return responses_added

async def generate_and_store_facts(landmark: dict, semantic_key: str, response: str):
    """Extract and store facts from a response."""
    try:
        # Use OpenAI to extract facts
        fact_extraction_prompt = f"""
        Extract key facts from this response about the landmark. Return only the facts as a JSON object with descriptive keys.
        
        Response: {response}
        
        Return format: {{"fact1": "description", "fact2": "description"}}
        """
        
        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        completion = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that extracts facts from text."},
                {"role": "user", "content": fact_extraction_prompt}
            ],
            temperature=0.3,
            max_tokens=300
        )
        
        facts_text = completion.choices[0].message.content.strip()
        
        # Parse JSON from response
        try:
            start_idx = facts_text.find('{')
            end_idx = facts_text.rfind('}') + 1
            if start_idx != -1 and end_idx > start_idx:
                json_str = facts_text[start_idx:end_idx]
                extracted_facts = json.loads(json_str)
                
                # Store each fact as a separate vector
                for fact_key, fact_text in extracted_facts.items():
                    advanced_s3_vector_service.add_fact(
                        fact_text=fact_text,
                        fact_key=fact_key,
                        landmark_id=landmark["name"].replace(" ", "_"),
                        metadata={
                            "semantic_key": semantic_key,
                            "source": "batch_extracted",
                            "extracted_at": datetime.utcnow().isoformat()
                        }
                    )
                
                print(f"✅ Extracted {len(extracted_facts)} facts for {landmark['name']} - {semantic_key}")
                
        except json.JSONDecodeError:
            print(f"⚠️ Failed to parse facts JSON for {landmark['name']} - {semantic_key}")
            
    except Exception as e:
        print(f"❌ Error extracting facts for {landmark['name']} - {semantic_key}: {e}")

async def main():
    """Main batch processing function."""
    print("🚀 Starting S3 Vector Search Batch Population")
    print("=" * 60)
    
    # Load configuration files
    configs = load_config_files()
    
    landmarks = configs.get("landmarks.json", [])
    semantic_config = configs.get("semantic_config.json", {})
    countries_data = configs.get("countries.json", {})
    interests_data = configs.get("interests.json", {})
    
    # Get lists for iteration
    countries = countries_data.get("countries", ["United States", "India", "Canada"])
    interests = interests_data.get("interests", ["Nature", "History", "Architecture"])
    ages = [25, 35, 55]  # Representative ages for each age group
    
    print(f"📊 Configuration:")
    print(f"   Landmarks: {len(landmarks)}")
    print(f"   Countries: {len(countries)}")
    print(f"   Interests: {len(interests)}")
    print(f"   Ages: {len(ages)}")
    print(f"   Total combinations per landmark: {len(countries) * len(interests) * len(ages)}")
    
    total_responses = 0
    total_facts = 0
    
    # Process each landmark
    for i, landmark in enumerate(landmarks, 1):
        print(f"\n{'='*60}")
        print(f"🏛️ Processing landmark {i}/{len(landmarks)}: {landmark['name']}")
        print(f"{'='*60}")
        
        # Get landmark info
        landmark_id = landmark["name"].replace(" ", "_")
        landmark_type = landmark.get("type", "tourist_attraction")
        
        # Create landmark-specific semantic key index
        print(f"🔧 Creating semantic key index for {landmark_id} (type: {landmark_type})")
        advanced_s3_vector_service._create_landmark_semantic_key_index(landmark_id, landmark_type)
        
        # Get semantic keys for this landmark type
        semantic_keys = get_relevant_semantic_keys(landmark_type, semantic_config)
        
        if not semantic_keys:
            print(f"⚠️ No semantic keys found for landmark type: {landmark_type}")
            continue
        
        # Populate responses for this landmark
        responses_added = await populate_landmark_responses(
            landmark=landmark,
            semantic_keys=semantic_keys,
            countries=countries,
            interests=interests,
            ages=ages,
            semantic_config=semantic_config
        )
        
        total_responses += responses_added
        
        # Generate facts for each semantic key (using a sample response)
        for semantic_key in semantic_keys:
            # Generate one sample response for fact extraction
            sample_response = await generate_landmark_response(
                landmark=landmark,
                semantic_key=semantic_key,
                user_country="United States",
                interest="History",
                age=35,
                semantic_config=semantic_config
            )
            
            if sample_response:
                await generate_and_store_facts(landmark, semantic_key, sample_response)
                total_facts += 1
        
        print(f"✅ Completed landmark {i}/{len(landmarks)}")
    
    print(f"\n🎉 Batch processing completed!")
    print(f"📊 Summary:")
    print(f"   Total landmarks processed: {len(landmarks)}")
    print(f"   Total responses added: {total_responses}")
    print(f"   Total facts extracted: {total_facts}")
    print(f"   Vector indexes populated: qa_index, fact_index")
    
    print(f"\n📋 Next Steps:")
    print(f"1. Test the new endpoints:")
    print(f"   - GET /landmark-response/")
    print(f"   - POST /ask-landmark-optimized")
    print(f"2. Monitor performance metrics")
    print(f"3. Adjust similarity thresholds as needed")

if __name__ == "__main__":
    asyncio.run(main()) 