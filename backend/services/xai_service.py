import os
import json
import logging
import requests
from typing import Optional
from dotenv import load_dotenv

from backend.services.xai_prompt_builder import build_track_prompt
from backend.services.xai_response_handler import parse_and_filter_tracks
from backend.services.xai_api_client import fetch_xai_tracks
from backend.config import TEST_JSON_DIR, ENABLE_ARTIST_DESCRIPTION, ENABLE_TRACK_DESCRIPTION, ENABLE_RANK_INTRO
from backend.utils.track_filters import validate_tracks

# Load environment variables
load_dotenv()

# 🧩 Shared fallback logger for this module (e.g., get_artist_description)
logger = logging.getLogger(__name__)

# 🎯 STEP-SPECIFIC LOGGERS for Step 1 substeps
logger_step1a = logging.getLogger("STEP_1.A")  # Prompt building
logger_step1b = logging.getLogger("STEP_1.B")  # Markdown/JSON parsing
logger_step1c = logging.getLogger("STEP_1.C")  # Validation + filtering

XAI_API_KEY = os.getenv("XAI_API_KEY")
XAI_API_URL = "https://api.x.ai/v1/chat/completions"
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "../schemas/track_schema.json")

with open(SCHEMA_PATH, "r") as f:
    TRACK_SCHEMA = json.load(f)


def get_top_tracks_from_xai(decade, genre, language, num_tracks, test_file_number=0):
    buffer_size = max(0, round(num_tracks * 0.25))
    total_requested = num_tracks + buffer_size

    logger_step1a.debug(f"[STEP_1.A] test_file_number={test_file_number}, num_tracks={num_tracks}, buffer={buffer_size}")
    logger_step1a.debug(f"[STEP_1.A] total_requested={total_requested}")
    logger_step1a.debug(f"[STEP_1.A] Building prompt for decade={decade}, genre={genre}, language={language}")

    prompt = build_track_prompt(decade, genre, total_requested, language, buffer_size)

    logger_step1b.debug("[STEP_1.B] Requesting top tracks from XAI...")
    tracks = []

    if test_file_number > 0:
        test_file_path = TEST_JSON_DIR / f"json_test_file_{test_file_number}.json"
        logger_step1b.debug(f"[TEST] Using {test_file_path}")
        try:
            with open(test_file_path, "r", encoding="utf-8") as test_file:
                test_json = json.load(test_file)
            raw_tracks = test_json.get("tracks", [])
            logger_step1b.debug(f"[TEST] Loaded {len(raw_tracks)} tracks.")
            tracks = parse_and_filter_tracks(json.dumps(raw_tracks), total_requested, is_test_mode=True)

            for t in tracks:
                rank = t.get("rank", 0)
                t["spotify_data"] = {
                    "spotify_track_id": f"test_track_{rank}",
                    "artist_id": f"test_artist_{rank}",
                    "duration_ms": 180000,
                    "popularity": 55,
                    "album_artwork": None,
                    "artist_artwork": None,
                    "artist_description": None,
                    "featured_artist_id": None,
                    "featured_artist_name": None,
                    "not_on_spotify": False
                }

        except Exception as e:
            logger_step1b.error(f"[ERROR] Failed to load test file: {e}")
    else:
        content = fetch_xai_tracks(prompt, test_file_number=test_file_number)
        if isinstance(content, list):
            logger_step1b.debug(f"[XAI] Received {len(content)} tracks.")
            tracks = content
        elif isinstance(content, str):
            tracks = parse_and_filter_tracks(content, num_tracks, is_test_mode=False)
        elif isinstance(content, dict):
            logger_step1b.debug(f"[XAI] Dict keys: {list(content.keys())}")
            raw_tracks = content.get("tracks", [])
            if not isinstance(raw_tracks, list):
                raise ValueError("Expected 'tracks' to be a list.")
            logger_step1b.debug(f"[XAI] Extracted {len(raw_tracks)} tracks.")
            tracks = parse_and_filter_tracks(json.dumps(raw_tracks), num_tracks, is_test_mode=False)
        else:
            raise TypeError(f"Unexpected content type: {type(content)}")

    valid_tracks = validate_tracks(tracks)
    logger_step1c.debug(f"[CLEANUP] {len(valid_tracks)} valid tracks after filtering (from {len(tracks)} total)")
    logger_step1c.debug(f"[CLEANUP] Returning {len(valid_tracks)} cleaned tracks from {total_requested} requested.")

    return {
        "language": language,
        "decade": decade,
        "genre": genre,
        "tracks": valid_tracks
    }


def get_track_descriptions_from_xai(track_data, language, decade, genre):
    if not ENABLE_TRACK_DESCRIPTION and not ENABLE_RANK_INTRO:
        logger.debug("🧮 Skipping description generation — no tokens used.")
        return {
            "language": language,
            "decade": decade,
            "genre": genre,
            "tracks": track_data.get("tracks", track_data)
        }

    tracks = track_data if isinstance(track_data, list) else track_data.get("tracks", [])
    batch_size = 10
    total = len(tracks)
    logger_step1c.debug(f"[BATCH] Processing {total} tracks in batches of {batch_size}...")

    for batch_index in range(0, total, batch_size):
        batch = tracks[batch_index:batch_index + batch_size]
        logger_step1c.debug(f"[BATCH] Processing batch {batch_index // batch_size + 1}")

        formatted_input = [
            {
                "rank": t.get("rank"),
                "decade": decade,
                "genre": genre,
                "trackName": t.get("trackName"),
                "artistName": t.get("artistName")
            } for t in batch
        ]

        requested_fields = []
        instructions = []

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

        joined_fields = ", ".join(requested_fields)
        prompt = (
            f"Generate the following fields in {language}: {joined_fields}. "
            + " ".join(instructions)
            + " Return only a valid JSON array with the requested fields.\n"
            f"Tracks:\n{json.dumps(formatted_input, indent=2)}"
        )

        headers = {
            "Authorization": f"Bearer {XAI_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "messages": [
                {"role": "system", "content": "You are an AI that returns valid JSON arrays only."},
                {"role": "user", "content": prompt}
            ],
            "model": "grok-2-latest",
            "stream": False,
            "temperature": 0.3
        }

        try:
            response = requests.post(XAI_API_URL, json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            batch_descriptions = json.loads(content)
            for i, desc in enumerate(batch_descriptions):
                tracks[batch_index + i].update(desc)
        except Exception as e:
            logger_step1c.error(f"[XAI ERROR] Failed to fetch descriptions: {e}")
            continue

    return {
        "language": language,
        "decade": decade,
        "genre": genre,
        "tracks": tracks
    }


def get_artist_description(artist_name: str, language: str = "English") -> Optional[str]:
    if not ENABLE_ARTIST_DESCRIPTION:
        logger.debug(f"[SKIP] Artist description disabled for {artist_name}.")
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

    logger.debug(f"[ARTIST] Requesting bio for: {artist_name}")

    try:
        response = requests.post(XAI_API_URL, json=payload, headers=headers)
        response.raise_for_status()
        result = response.json()
        content = result["choices"][0]["message"]["content"]

        if not content.strip():
            logger.warning(f"[EMPTY] No content returned for: {artist_name}")
            return f"(No description found for {artist_name})"

        return content.strip()

    except requests.exceptions.HTTPError as e:
        logger.error(f"[HTTP ERROR] {e}")
        return f"(HTTP error fetching description for {artist_name})"

    except Exception as e:
        logger.error(f"[ERROR] Unexpected issue: {e}")
        return f"(Unexpected error fetching description for {artist_name})"
