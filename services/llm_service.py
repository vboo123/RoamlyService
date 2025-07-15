import os
import json
import openai
from typing import Optional

class LLMService:
    def __init__(self):
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        if self.openai_api_key:
            self.client = openai.OpenAI(api_key=self.openai_api_key)
        else:
            self.client = None
            print("⚠️ Warning: OPENAI_API_KEY not found. LLM fallbacks will not work.")
    
    async def generate_response(self, question: str, landmark_id: str, landmark_type: str, user_country: str, interest: str) -> str:
        """
        Generate LLM response for a question about a landmark.
        Uses the same configuration as the batch script.
        """
        try:
            if self.client:
                return await self._generate_openai_response(question, landmark_id, landmark_type, user_country, interest)
            else:
                return f"I'm sorry, I couldn't generate a response for that question about {landmark_id}. Please try asking something else."
        except Exception as e:
            print(f"🔥 ERROR in LLM generation: {e}")
            return f"I'm sorry, I couldn't generate a response for that question about {landmark_id}. Please try asking something else."
    
    async def _generate_openai_response(self, question: str, landmark_id: str, landmark_type: str, user_country: str, interest: str) -> str:
        """
        Generate response using OpenAI API with same configuration as batch script.
        """
        try:
            # Create context-aware prompt similar to batch script
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
            
            # Use same configuration as batch script
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a friendly and knowledgeable travel guide."},
                    {"role": "user", "content": context_prompt}
                ],
                temperature=0.7,
                max_tokens=500
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"OpenAI API error: {e}")
            raise

    async def generate_response_with_prompt_and_age(
        self, prompt: str, question: str, landmark_id: str, 
        user_country: str, interest: str, age_group: str
    ) -> str:
        """Generate response using a custom prompt with age_group (like batch script)"""
        try:
            # Format the prompt with all variables (including age_group)
            formatted_prompt = prompt.format(
                landmark=landmark_id.replace("_", " "),
                userCountry=user_country,
                mappedCategory=interest,
                age_group=age_group
            )
            
            # ✅ FIX: Use the formatted prompt directly instead of calling generate_response
            if self.client:
                # Add the user's question to the formatted prompt
                full_prompt = f"{formatted_prompt}\n\nUser Question: {question}\n\nResponse:"
                
                response = self.client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "You are a friendly and knowledgeable travel guide."},
                        {"role": "user", "content": full_prompt}
                    ],
                    temperature=0.7,
                    max_tokens=500
                )
                return response.choices[0].message.content.strip()
            else:
                return f"I'm sorry, I couldn't generate a response for that question about {landmark_id}. Please try asking something else."
            
        except Exception as e:
            print(f"Error generating response with custom prompt and age: {e}")
            return f"I apologize, but I'm unable to provide specific information about {landmark_id.replace('_', ' ')} at the moment. Please try asking a different question."

# Global instance
llm_service = LLMService() 