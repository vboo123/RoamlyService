import os
import json
import openai
from typing import Optional
from gpt4all import GPT4All

class LLMService:
    def __init__(self):
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.use_local_llm = os.getenv("USE_LOCAL_LLM", "false").lower() == "true"
    
    async def generate_response(self, question: str, landmark_id: str, landmark_type: str, user_country: str, interest: str) -> str:
        """
        Generate LLM response for a question about a landmark.
        """
        try:
            if self.openai_api_key and not self.use_local_llm:
                return await self._generate_openai_response(question, landmark_id, landmark_type, user_country, interest)
            else:
                return await self._generate_local_llm_response(question, landmark_id, landmark_type, user_country, interest)
        except Exception as e:
            print(f"🔥 ERROR in LLM generation: {e}")
            return f"I'm sorry, I couldn't generate a response for that question about {landmark_id}. Please try asking something else."
    
    async def _generate_openai_response(self, question: str, landmark_id: str, landmark_type: str, user_country: str, interest: str) -> str:
        """
        Generate response using OpenAI API.
        """
        # Load semantic config for prompt template
        with open("scripts/semantic_config.json", "r") as f:
            semantic_config = json.load(f)
        
        # Get a general prompt template for this landmark type
        available_keys = list(semantic_config.get(landmark_type, {}).keys())
        if available_keys:
            prompt_template = semantic_config[landmark_type][available_keys[0]]
        else:
            prompt_template = "You are a knowledgeable local tour guide. Answer the user's question about {landmark} in a friendly, informative way."
        
        # Create context-aware prompt
        context_prompt = f"""
        You are a knowledgeable local tour guide. A traveler from {user_country} who enjoys {interest} is asking about {landmark_id.replace('_', ' ')}.
        
        Question: {question}
        
        Please provide a helpful, engaging response that's:
        - Accurate and informative
        - Tailored to someone interested in {interest}
        - Friendly and conversational
        - Under 200 words
        - Easy to read out loud
        """
        
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a friendly and knowledgeable travel guide."},
                    {"role": "user", "content": context_prompt}
                ],
                temperature=0.7,
                max_tokens=300
            )
            return response['choices'][0]['message']['content'].strip()
        except Exception as e:
            print(f"OpenAI API error: {e}")
            raise
    
    async def _generate_local_llm_response(self, question: str, landmark_id: str, landmark_type: str, user_country: str, interest: str) -> str:
        """
        Generate response using local GPT4All model.
        """
        try:
            model = GPT4All(model_name='Meta-Llama-3-8B-Instruct.Q4_0.gguf', allow_download=False)
            
            prompt = f"""
            You are a knowledgeable local tour guide. A traveler from {user_country} who enjoys {interest} is asking about {landmark_id.replace('_', ' ')}.
            
            Question: {question}
            
            Please provide a helpful, engaging response that's accurate, friendly, and under 200 words.
            """
            
            response = ""
            for token in model.generate(prompt, streaming=True, max_tokens=300):
                response += token
            
            return response.strip()
        except Exception as e:
            print(f"Local LLM error: {e}")
            raise

# Global instance
llm_service = LLMService() 