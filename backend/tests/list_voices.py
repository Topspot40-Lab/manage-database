import os, requests
from dotenv import load_dotenv
load_dotenv()

API_KEY = os.getenv("ELEVENLABS_API_KEY")
assert API_KEY, "ELEVENLABS_API_KEY missing"

url = "https://api.elevenlabs.io/v1/voices"
resp = requests.get(url, headers={"xi-api-key": API_KEY})
resp.raise_for_status()
data = resp.json()

print("\n=== Voices in your account ===\n")
for v in data.get("voices", []):
    print(f"{v['name']:15s} | {v['voice_id']} | labels={v.get('labels')} | desc={v.get('description')}")
