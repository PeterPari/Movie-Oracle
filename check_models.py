import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

try:
    print("Listing available models...")
    # The SDK might have a different way to list models, let's try the standard way
    # usually client.models.list() or similar. 
    # Based on the new SDK, it's often client.models.list()
    
    for m in client.models.list():
        if "generateContent" in m.supported_generation_methods:
            print(f"- {m.name}")
            
except Exception as e:
    print(f"Error: {e}")
