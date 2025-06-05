# backend/services/xai_track_descriptions.py

import json
import logging
import requests
from backend.config import XAI_API_KEY, XAI_API_URL, BATCH_SIZE

def get_track_descriptions_from_xai(track_data, language, category, genre):
    tracks = track_data if isinstance(track_data, list) else track_data.get("tracks", [])

    for batch_index in range(0, len(tracks), BATCH_SIZE):
        batch = tracks[batch_index:batch_index + BATCH_SIZE]
        formatted_input = [
            {
                "rank": t.get("rank"),
                "category": category,
                "genre": genre,
                "trackName": t.get("trackName"),
                "artistName": t.get("artistName")
            }
            for t in batch
        ]

        prompt = (
            f"Generate an 'intro' and 'detail' field in {language} for each of the following tracks. "
            "Each 'intro' should be short and unique. Each 'detail' should be a rich Casey Kasem-style narrative, "
            "without repeating the intro info.\n\n"
            f"Tracks:\n{json.dumps(formatted_input, indent=2)}"
        )

        payload = {
            "messages": [
                {"role": "system", "content": "Return valid JSON only."},
                {"role": "user", "content": prompt}
            ],
            "model": "grok-2-latest",
            "stream": False,
            "temperature": 0.3
        }

        try:
            response = requests.post(XAI_API_URL, json=payload, headers={
                "Authorization": f"Bearer {XAI_API_KEY}",
                "Content-Type": "application/json"
            })
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            batch_descriptions = json.loads(content)

            for i, desc in enumerate(batch_descriptions):
                tracks[batch_index + i].update(desc)

        except Exception as e:
            logging.error(f"❌ Error processing batch {batch_index // BATCH_SIZE + 1}: {e}")

    return {
        "language": language,
        "category": category,
        "genre": genre,
        "tracks": tracks
    }
