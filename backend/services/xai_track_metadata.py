# backend/services/xai_track_metadata.py

# import json
import logging
import requests
from backend.config import XAI_API_KEY, XAI_API_URL
from backend.services.xai_prompt_builder import build_track_prompt
from backend.services.xai_response_handler import parse_and_filter_tracks

def get_top_tracks_from_xai(category, genre, num_tracks, language):
    buffer_size = 4 if num_tracks >= 40 else 1
    prompt = build_track_prompt(category, genre, num_tracks, language, buffer_size)

    logging.info("🎵 Requesting top tracks from XAI...")
    headers = {
        "Authorization": f"Bearer {XAI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "messages": [
            {"role": "system", "content": "You are an AI that returns valid JSON arrays."},
            {"role": "user", "content": prompt}
        ],
        "model": "grok-2-latest",
        "stream": False,
        "temperature": 0.3
    }

    try:
        response = requests.post(XAI_API_URL, json=payload, headers=headers)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logging.error(f"❌ Failed to fetch tracks from XAI: {e}")
        return []

    return {
        "language": language,
        "category": category,
        "genre": genre,
        "tracks": parse_and_filter_tracks(content, num_tracks)
    }
