import os
import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("ELEVENLABS_API_KEY")

url = "https://api.elevenlabs.io/v1/voices"
headers = {
    "xi-api-key": API_KEY
}

response = requests.get(url, headers=headers)

if response.status_code != 200:
    print("❌ Error:", response.status_code)
    print(response.text)
else:
    print("✅ Voices in your account:\n")
    voices = response.json().get("voices", [])
    for v in voices:
        print(f"Name: {v['name']}")
        print(f"Voice ID: {v['voice_id']}")
        print(f"Category: {v.get('category', 'N/A')}")
        print("-" * 40)
