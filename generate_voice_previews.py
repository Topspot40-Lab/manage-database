import os
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("ELEVENLABS_API_KEY")
MODEL_ID = os.getenv("ELEVENLABS_MODEL", "eleven_monolingual_v1")
STABILITY = float(os.getenv("VOICE_STABILITY", 0.5))
SIMILARITY = float(os.getenv("VOICE_SIMILARITY", 0.75))

# 🎧 Output folder
PREVIEW_DIR = Path("data/mp3_files/voice_preview")
PREVIEW_DIR.mkdir(parents=True, exist_ok=True)

# 🗣️ Test line for all voices
TEST_LINE = "Howdy! This is a voice preview for the TopSpot program."

def get_all_voices():
    url = "https://api.elevenlabs.io/v1/voices"
    headers = {"xi-api-key": API_KEY}
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print("❌ Failed to fetch voices:", response.status_code)
        print(response.text)
        return []
    return response.json().get("voices", [])

def generate_preview_mp3(voice_id: str, voice_name: str):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": TEST_LINE,
        "model_id": MODEL_ID,
        "voice_settings": {
            "stability": STABILITY,
            "similarity_boost": SIMILARITY
        }
    }

    response = requests.post(url, json=payload, headers=headers)
    if response.status_code != 200:
        print(f"❌ Error for {voice_name} ({voice_id}):", response.status_code)
        return

    safe_name = voice_name.lower().replace(" ", "_")
    file_path = PREVIEW_DIR / f"{safe_name}_{voice_id}.mp3"
    with open(file_path, "wb") as f:
        f.write(response.content)
    print(f"✅ Saved preview: {file_path}")

def main():
    voices = get_all_voices()
    print(f"\n🎙️ Generating previews for {len(voices)} voices...\n")
    for v in voices:
        generate_preview_mp3(v["voice_id"], v["name"])
    print("\n✅ All previews generated!")

if __name__ == "__main__":
    main()
