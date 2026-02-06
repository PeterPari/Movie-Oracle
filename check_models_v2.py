from google import genai
import os
from dotenv import load_dotenv

load_dotenv()

try:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not found in environment variables.")
    else:
        client = genai.Client(api_key=api_key)
        print("Available models:")
        for model in client.models.list():
            print(model.name)
except Exception as e:
    print(f"An error occurred: {e}")
