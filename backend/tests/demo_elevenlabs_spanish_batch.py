# backend/tests/demo_elevenlabs_spanish_batch.py
import os
from pathlib import Path
import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("ELEVENLABS_API_KEY")
assert API_KEY, "ELEVENLABS_API_KEY missing (set in .env or env)"

OUT = Path("tts_demos/elevenlabs")
OUT.mkdir(parents=True, exist_ok=True)

# You can put either a display NAME or a VOICE ID on the right-hand side.
# Names will be resolved to IDs automatically.
voice_map = {
    "Valentina_esMX": "Valentina",
    "Adriana_esMX":   "Adriana",
    "Maria_esES":     "María",
    "Alejandro_latam":"Alejandro",
}

# 1) Fetch your voices so we can resolve names -> IDs
def fetch_voices():
    resp = requests.get(
        "https://api.elevenlabs.io/v1/voices",
        headers={"xi-api-key": API_KEY}
    )
    if resp.status_code == 401:
        raise SystemExit("401 Unauthorized listing voices. Check ELEVENLABS_API_KEY.")
    resp.raise_for_status()
    data = resp.json()
    by_name = {}
    by_id = {}
    for v in data.get("voices", []):
        name = v.get("name", "")
        vid = v.get("voice_id", "")
        by_name[name.lower()] = vid
        by_id[vid] = name
    return by_name, by_id, data.get("voices", [])
