from pathlib import Path
import requests
from backend.config import (
    ELEVENLABS_API_KEY,
    ELEVENLABS_MODEL,
    VOICE_STABILITY,
    VOICE_SIMILARITY
)


def generate_tts_mp3(text: str, out_path: Path, voice_id: str, overwrite: bool = False):
    if out_path.exists() and not overwrite:
        print(f"⚠️ Skipping TTS: File already exists → {out_path}")
        return

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }

    payload = {
        "text": text,
        "model_id": ELEVENLABS_MODEL,
        "voice_settings": {
            "stability": VOICE_STABILITY,
            "similarity_boost": VOICE_SIMILARITY
        }
    }

    response = requests.post(url, json=payload, headers=headers)
    if response.status_code != 200:
        raise RuntimeError(f"❌ ElevenLabs error: {response.status_code} — {response.text}")

    # ✅ Correct
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(response.content)

    print(f"✅ TTS generated: {out_path}")

