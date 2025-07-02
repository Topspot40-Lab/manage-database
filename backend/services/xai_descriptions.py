# backend/services/xai_descriptions.py

import json, requests, logging
from typing import Optional

from backend.config import (
    ENABLE_TRACK_DESCRIPTION,
    ENABLE_RANK_INTRO,
    ENABLE_ARTIST_DESCRIPTION,
    XAI_API_KEY,
    XAI_API_URL,
)
from backend.utils.logger_factory import get_step_logger

logger_step2 = get_step_logger("STEP_2")

def get_track_descriptions_from_xai(track_data, language, decade, genre):
    if not ENABLE_TRACK_DESCRIPTION and not ENABLE_RANK_INTRO:
        logger_step2.info("🧮 Skipping STEP 2 description generation — no tokens used.")
        return {
            "language": language,
            "decade": decade,
            "genre": genre,
            "tracks": track_data.get("tracks", track_data)
        }

    tracks = track_data if isinstance(track_data, list) else track_data.get("tracks", [])
    total = len(tracks)
    batch_size = 10

    logger_step2.info(f"✍️ STEP 2: Enriching {total} tracks with XAI descriptions (batch={batch_size})")

    for batch_start in range(0, total, batch_size):
        batch_end = min(batch_start + batch_size, total)
        batch = tracks[batch_start:batch_end]
        batch_num = (batch_start // batch_size) + 1
        logger_step2.info(f"   • Batch {batch_num}: tracks {batch_start+1}-{batch_end}")

        formatted_input = [
            {
                "rank": t.get("rank"),
                "decade": decade,
                "genre": genre,
                "trackName": t.get("trackName"),
                "artistName": t.get("artistName"),
            }
            for t in batch
        ]

        requested_fields, instructions = [], []
        if ENABLE_RANK_INTRO:
            requested_fields.append("intro")
            instructions.append(
                "Each 'intro' should be a short one-liner with rank, decade, genre, track name, and artist name."
            )
        if ENABLE_TRACK_DESCRIPTION:
            requested_fields.append("detail")
            instructions.append(
                "Each 'detail' should be a narrative in Casey Kasem's style, avoiding repetition from the intro."
            )

        prompt = (
            f"Generate the following fields in {language}: {', '.join(requested_fields)}. "
            + " ".join(instructions)
            + " Return only a valid JSON array.\n"
            f"Tracks:\n{json.dumps(formatted_input, indent=2)}"
        )

        payload = {
            "messages": [
                {"role": "system", "content": "You are an AI that returns valid JSON arrays only."},
                {"role": "user", "content": prompt}
            ],
            "model": "grok-2-latest",
            "stream": False,
            "temperature": 0.3
        }

        headers = {
            "Authorization": f"Bearer {XAI_API_KEY}",
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(XAI_API_URL, json=payload, headers=headers)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]

            batch_descriptions = json.loads(content)
            for i, desc in enumerate(batch_descriptions):
                tracks[batch_start + i].update(desc)
                logger_step2.debug(
                    f"✅ Rank {tracks[batch_start + i].get('rank')}: intro={'intro' in desc}, detail={'detail' in desc}"
                )

        except Exception as e:
            logger_step2.error(f"[XAI ERROR] Batch {batch_num}: {e}")
            continue

    logger_step2.info("✅ STEP 2 complete.")
    return {
        "language": language,
        "decade": decade,
        "genre": genre,
        "tracks": tracks
    }


def get_artist_description(artist_name: str, language: str = "English") -> Optional[str]:
    if not ENABLE_ARTIST_DESCRIPTION:
        logger_step2.debug(f"[SKIP] Artist description disabled for {artist_name}.")
        return None

    prompt = (
        f"Write a short artist biography in {language} for '{artist_name}'. "
        "Include nationality, genre, early story, key achievements, and trivia. "
        "Keep it short (2–3 sentences) with no formatting."
    )

    headers = {
        "Authorization": f"Bearer {XAI_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "messages": [
            {"role": "system", "content": "You return plain-text artist bios only."},
            {"role": "user", "content": prompt}
        ],
        "model": "grok-2-latest",
        "stream": False,
        "temperature": 0.5
    }

    logger_step2.debug(f"[ARTIST] Requesting bio for: {artist_name}")

    try:
        response = requests.post(XAI_API_URL, json=payload, headers=headers)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]

        if not content.strip():
            logger_step2.warning(f"[EMPTY] No content returned for: {artist_name}")
            return f"(No description found for {artist_name})"

        return content.strip()

    except requests.exceptions.HTTPError as e:
        logger_step2.error(f"[HTTP ERROR] {e}")
        return f"(HTTP error fetching description for {artist_name})"

    except Exception as e:
        logger_step2.error(f"[ERROR] Unexpected issue: {e}")
        return f"(Unexpected error fetching description for {artist_name})"
