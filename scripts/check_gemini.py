from dotenv import load_dotenv
import os
load_dotenv()

key = os.getenv("GEMINI_API_KEY", "")
print(f"Key loaded: {key[:15]}... (length: {len(key)})")

try:
    from google import genai
    client = genai.Client(api_key=key)
    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents="Say exactly: Gemini is connected and working!"
    )
    print(f"Gemini response: {response.text.strip()}")
    print("Gemini API: OK")
except Exception as e:
    print(f"ERROR: {e}")
