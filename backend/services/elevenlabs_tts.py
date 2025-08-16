# backend/services/elevenlabs_tts.py
import requests
from backend.config import ELEVEN_MODEL_ID
from backend.services.tts_profiles import get_tts_profile

ELEVEN_BASE = "https://api.elevenlabs.io/v1"

def synth_to_mp3_bytes(text: str, lang: str, kind: str, api_key: str) -> bytes:
    prof = get_tts_profile(lang, kind)
    url = f"{ELEVEN_BASE}/text-to-speech/{prof['voice_id']}"
    headers = {"xi-api-key": api_key, "accept": "audio/mpeg", "content-type": "application/json"}
    payload = {"text": text, "model_id": ELEVEN_MODEL_ID, "voice_settings": prof.get("settings", {})}
    r = requests.post(url, headers=headers, json=payload, timeout=60)
    r.raise_for_status()
    return r.content
