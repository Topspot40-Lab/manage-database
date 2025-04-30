import os
import json
import logging
import requests
from jsonschema import validate, ValidationError
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s]: %(message)s")

# Constants
XAI_API_KEY = os.getenv("XAI_API_KEY")
XAI_API_URL = "https://api.x.ai/v1/chat/completions"
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "../schemas/track_schema.json")

# Load schema once at startup
with open(SCHEMA_PATH, "r") as f:
    TRACK_SCHEMA = json.load(f)


def validate_tracks(tracks):
    """Validate tracks against schema."""
    try:
        validate(instance=tracks, schema=TRACK_SCHEMA)
        return True
    except ValidationError as e:
        logging.error(f"❌ Schema validation failed: {e.message}")
        return False


def get_top_tracks_from_xai(category, genre, num_tracks, language):
    """
    Get top track metadata from XAI (rank, name, artist, year).
    Return wrapped in new JSON format.
    """
    prompt = (
        f"Generate a JSON array with exactly {num_tracks} top tracks from the {genre} genre "
        f"of the {category} decade for a {language} audience. "
        "Each entry must include: rank (integer), trackName (string), artistName (string), and yearReleased (integer). "
        "Do NOT include descriptions, intros, or any extra text—just return a valid JSON array."
    )

    headers = {
        "Authorization": f"Bearer {XAI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "messages": [
            {"role": "system", "content": "You are an AI that strictly returns valid JSON arrays with no extra text."},
            {"role": "user", "content": prompt}
        ],
        "model": "grok-2-latest",
        "stream": False,
        "temperature": 0.3
    }

    try:
        logging.info("🎵 Requesting top track names from XAI...")
        response = requests.post(XAI_API_URL, json=payload, headers=headers)
        response.raise_for_status()
        result = response.json()

        content = result["choices"][0]["message"]["content"]
        tracks = json.loads(content)

        if validate_tracks(tracks):
            wrapped = {
                "language": language,
                "category": category,
                "genre": genre,
                "tracks": tracks
            }
            logging.info(f"✅ Wrapped and returned {len(tracks)} tracks in new JSON format.")
            return wrapped
        else:
            raise ValueError("XAI returned invalid track format.")
    except Exception as e:
        logging.error(f"❌ XAI call failed or unexpected response: {e}")
        raise


def get_track_descriptions_from_xai(track_data, language, category, genre):
    """
    Adds 'intro' and 'detail' to each track. Returns updated full JSON structure.
    """
    tracks = track_data if isinstance(track_data, list) else track_data.get("tracks", [])

    batch_size = 10
    total = len(tracks)
    logging.info(f"📝 Processing {total} tracks in batches of {batch_size}...")

    for batch_index in range(0, total, batch_size):
        batch = tracks[batch_index:batch_index + batch_size]
        logging.info(f"🔹 Processing batch {batch_index // batch_size + 1}")

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
            "Each 'intro' should be a short, engaging one-liner that introduces the track, explicitly using the provided rank, category, genre, track name, and artist name. "
            "Ensure variety in sentence structure to avoid repetition. "
            "Each 'detail' should be a rich, engaging narrative in the style of Casey Kasem, including interesting facts about the song, artist, year of release, and cultural impact. "
            "The 'detail' field MUST NOT repeat the rank, category, genre, track name, or artist name. "
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
                {"role": "system", "content": "You are an AI that strictly returns valid JSON arrays with no extra text."},
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
        "category": category,
        "genre": genre,
        "tracks": tracks
    }
