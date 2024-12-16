from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

# api_key = os.getenv("OPENAI_API_KEY")
api_key = "sdsd"
client = OpenAI(api_key=api_key)

response = client.chat.completions.create(
  model="gpt-4o-mini",
messages=[
        {"role": "user", "content": "Hello, how are you?"}
    ],  response_format={
    "type": "text"
  },
  temperature=1,
  max_completion_tokens=2048,
  top_p=1,
  frequency_penalty=0,
  presence_penalty=0
)

print(response)