import os
import json
import logging
import requests
from jsonschema import validate, ValidationError
from dotenv import load_dotenv

from backend.services.xai_prompt_builder import build_track_prompt
from backend.services.xai_response_handler import parse_and_filter_tracks
from backend.services.xai_api_client import fetch_xai_tracks
from backend.config import TEST_JSON_DIR

print(f"📂 Current working directory: {os.getcwd()}")

# Load environment variables
load_dotenv()

# Setup logging
logger = logging.getLogger(__name__)

# Constants
XAI_API_KEY = os.getenv("XAI_API_KEY")
XAI_API_URL = "https://api.x.ai/v1/chat/completions"
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "../schemas/track_schema.json")

# Load schema once at startup
with open(SCHEMA_PATH, "r") as f:
    TRACK_SCHEMA = json.load(f)

def validate_tracks(data):
    """Validate the full wrapped track data against the schema."""
    try:
        validate(instance=data, schema=TRACK_SCHEMA)
        return True
    except ValidationError as e:
        logging.error(f"❌ Schema validation failed: {e.message}")
        return False

def get_top_tracks_from_xai(decade, genre, language, num_tracks, test_file_number=0):


    buffer_size = 4 if num_tracks >= 40 else 1
    prompt = build_track_prompt(decade, genre, num_tracks, language, buffer_size)
    logging.info("🎵 Requesting top tracks from XAI...")
    tracks = []

    if test_file_number > 0:
        test_file_path = TEST_JSON_DIR / f"json_test_file_{test_file_number}.json"
        logging.info(f"🧪 Loading test data from {test_file_path}")
        try:
            with open(test_file_path, "r", encoding="utf-8") as test_file:
                test_json = json.load(test_file)
            raw_tracks = test_json.get("tracks", [])
            tracks = parse_and_filter_tracks(json.dumps(raw_tracks), num_tracks, is_test_mode=True)
        except Exception as e:
            logging.error(f"❌ Failed to load test file: {e}")
    else:
        content = fetch_xai_tracks(prompt)
        if isinstance(content, list):
            tracks = content
        else:
            tracks = parse_and_filter_tracks(content, num_tracks, is_test_mode=False)

    return {
        "language": language,
        "decade": decade,
        "genre": genre,
        "tracks": tracks
    }

def get_track_descriptions_from_xai(track_data, language, decade, genre):
    tracks = track_data if isinstance(track_data, list) else track_data.get("tracks", [])
    batch_size = 10
    total = len(tracks)
    logging.debug(f"📝 Processing {total} tracks in batches of {batch_size}...")

    for batch_index in range(0, total, batch_size):
        batch = tracks[batch_index:batch_index + batch_size]
        logging.info(f"🔹 Processing batch {batch_index // batch_size + 1}")

        formatted_input = [
            {
                "rank": t.get("rank"),
                "decade": decade,
                "genre": genre,
                "trackName": t.get("trackName"),
                "artistName": t.get("artistName")
            }
            for t in batch
        ]

        prompt = (
            f"Generate an 'intro' and 'detail' field in {language} for each of the following tracks. "
            "Each 'intro' should be a short, engaging one-liner that introduces the track, explicitly using the provided rank, decade, genre, track name, and artist name. "
            "Ensure variety in sentence structure to avoid repetition. "
            "Each 'detail' should be a rich, engaging narrative in the style of Casey Kasem, including interesting facts about the song, artist, year of release, and cultural impact. "
            "The 'detail' field MUST NOT repeat the rank, decade, genre, track name, or artist name. "
            "Format the response strictly as a JSON array with the same number of entries as provided. "
            "Return only a valid JSON array with:\n"
            "- 'intro'\n"
            "- 'detail'\n"
            f"Tracks:\n{json.dumps(formatted_input, indent=2)}"
        )

        headers = {
            "Authorization": f"Bearer {XAI_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "messages": [
                {"role": "system",
                 "content": "You are an AI that strictly returns valid JSON arrays with no extra text."},
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
            logging.error(f"❌ Failed to fetch descriptions from XAI: {e}")
            continue

    return {
        "language": language,
        "decade": decade,
        "genre": genre,
        "tracks": tracks
    }

def get_artist_description(artist_name: str, language: str = "English") -> str:
    prompt = (
        f"Write a short artist biography in {language} for the musician named '{artist_name}'. "
        "Include their nationality, genre, early life or origin story, notable achievements, and any personal or cultural trivia of interest. "
        "Keep it concise (2–3 sentences), engaging, and informative. Do not include any JSON formatting or tags—just return plain text."
    )

    headers = {
        "Authorization": f"Bearer {os.getenv('XAI_API_KEY')}",
        "Content-Type": "application/json"
    }

    payload = {
        "messages": [
            {
                "role": "system",
                "content": "You are an AI that returns short, plain-text artist biographies with no formatting or markup."
            },
            {"role": "user", "content": prompt}
        ],
        "model": "grok-2-latest",
        "stream": False,
        "temperature": 0.5
    }

    logging.debug(f"📨 Prompt sent to XAI:\n{json.dumps(payload, indent=2)}")

    try:
        logging.info(f"📚 Requesting artist bio for: {artist_name}")
        response = requests.post(XAI_API_URL, json=payload, headers=headers)

        if response.status_code != 200:
            logging.error(f"❌ XAI rejected the request with status {response.status_code}")
            logging.error(f"🦾 Response body:\n{response.text}")
            logging.error(f"📬 Payload sent:\n{json.dumps(payload, indent=2)}")
            raise requests.exceptions.HTTPError(response.text)

        result = response.json()
        logging.debug(f"📦 XAI Response JSON:\n{json.dumps(result, indent=2)}")
        content = result["choices"][0]["message"]["content"]

        if not content.strip():
            logging.warning(f"⚠️ Empty description returned for artist: {artist_name}")
            print(f"⚠️ XAI returned EMPTY content for {artist_name}")
            return f"(No description found for {artist_name})"
        return content.strip()

    except requests.exceptions.HTTPError as e:
        try:
            logging.error(f"❌ HTTPError: {e}")
            logging.error(f"🦾 Response body:\n{e.response.text}")
        except Exception as log_err:
            logging.error(f"⚠️ Could not log response body: {log_err}")
        return f"(HTTP error fetching description for {artist_name})"

    except Exception as e:
        logging.error(f"❌ Unexpected error: {e}")
        return f"(Unexpected error fetching description for {artist_name})"
