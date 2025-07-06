import os
import json
import logging
from dotenv import load_dotenv
from backend.utils.mode_utils import ModeFlag

from backend.services.xai_prompt_builder import build_track_prompt
from backend.services.xai_response_handler import parse_and_filter_tracks
from backend.services.xai_api_client import fetch_xai_tracks
from backend.config import TEST_JSON_DIR
from backend.utils.track_filters import validate_tracks

# Load environment variables
load_dotenv()

# 🧩 Shared fallback logger for this module (e.g., get_artist_description)
logger = logging.getLogger(__name__)

def format_track_list(tracks, fields=("rank", "track_name", "artist_name", "mode_flag")) -> str:
    """
    Return a formatted string with aligned columns for selected track fields.
    Adds visual spacing or prefix to non-'solo' mode_flag values for better scanning.
    """
    if not tracks:
        return "⚠️ No tracks to display."

    # Column widths
    field_widths = {
        "rank": 4,
        "track_name": 40,
        "artist_name": 45,
        "mode_flag": 12,  # Make a bit wider for prefix
    }

    # Helper to format mode_flag visually
    def format_mode_flag(flag):  # ✅ no shadowing
        ...
        try:
            name = ModeFlag(flag).name.lower()
        except (ValueError, AttributeError):
            name = str(flag).lower()

        if name == "solo":
            return " solo"
        elif name == "duet":
            return "→→  duet"
        elif name == "featured":
            return "→→→ feat"
        elif name == "group":
            return "→→→→ group"
        else:
            return f" {name[:10].strip()}"

    # Header line
    header = " | ".join(f"{field:<{field_widths[field]}}" for field in fields)
    separator = "-" * len(header)
    lines = ["🎧 Track summary:", header, separator]

    # Data rows
    for track in tracks:
        row = []
        for field in fields:
            value = track.get(field, "")
            if field == "mode_flag":
                value = format_mode_flag(value)
            row.append(str(value).ljust(field_widths[field])[:field_widths[field]])
        lines.append(" | ".join(row))

    return "\n".join(lines)


def get_step_logger(name: str, fallback: str = "STEP_1") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.level == logging.NOTSET:
        # fallback only if no level explicitly set
        return logging.getLogger(fallback)
    return logger

# 🎯 STEP-SPECIFIC LOGGERS for Step 1 sub-steps (with fallback to STEP_1)
logger_step1a = get_step_logger("STEP_1.A")
logger_step1b = get_step_logger("STEP_1.B")
logger_step1c = get_step_logger("STEP_1.C")
logger_step1  = get_step_logger("STEP_1")   # 🔄 Fallback logger for all of Step 1

XAI_API_KEY = os.getenv("XAI_API_KEY")
XAI_API_URL = "https://api.x.ai/v1/chat/completions"
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "../schemas/track_schema.json")

with open(SCHEMA_PATH, "r") as f:
    TRACK_SCHEMA = json.load(f)


def get_top_tracks_from_xai(decade, genre, language, num_tracks, test_file_number=0):
    if test_file_number > 0:
        buffer_size = 0
    else:
       buffer_size = max(0, round(num_tracks * 0.10))

    total_requested = num_tracks + buffer_size


    logger_step1a.debug(
        f"[STEP_1.A] test_file_number={test_file_number}, num_tracks={num_tracks}, buffer={buffer_size}, "
        f"total_requested={total_requested}, decade={decade}, genre={genre}, language={language}"
    )

    prompt = build_track_prompt(decade, genre, total_requested, language, buffer_size)

    logger_step1b.debug("[STEP_1.B] Requesting top tracks from XAI...")
    tracks = []
    # ---------------------------------------------------------------------------
    # Add this near the other logger defs, right after logger_step1b/c declarations
    logger_step1 = get_step_logger("STEP_1")  # fallback for the whole step
    # ---------------------------------------------------------------------------


    if test_file_number > 0:
        test_file_path = TEST_JSON_DIR / f"json_test_file_{test_file_number}.json"
        logger_step1b.debug(f"[STEP_1.B] [TEST] Using {test_file_path}")
        try:
            with open(test_file_path, "r", encoding="utf-8") as test_file:
                test_json = json.load(test_file)
            raw_tracks = test_json.get("tracks", [])
            logger_step1b.debug(f"[STEP_1.B] [TEST] Loaded {len(raw_tracks)} tracks.")

            # Parse + filter
            tracks = parse_and_filter_tracks(
                json.dumps(raw_tracks), total_requested, is_test_mode=True
            )

            # 🧩 NEW: summary only if STEP_1.B OR STEP_1 is at DEBUG
            if logger_step1b.isEnabledFor(logging.INFO) or logger_step1.isEnabledFor(logging.INFO):
                if tracks:
                    summary_header = "🎧 [STEP_1.B] [TEST] Tracks loaded from fixture:\n🎧 Track summary:"
                    # logger_step1b.info(summary_header + "\n" + format_track_list(tracks))
                    logger_step1b.info(format_track_list(tracks))
                else:
                    logger_step1b.warning("⚠️ [TEST] No tracks loaded from fixture.")

            # Stub Spotify data so later steps don’t crash
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
                    "not_on_spotify": False,
                }

        except Exception as e:
            logger_step1b.error(f"[ERROR] Failed to load test file: {e}")

    else:
        # … (unchanged XAI call & isinstance tree)
        content = fetch_xai_tracks(prompt, test_file_number=test_file_number)

        # 🧠 STEP_1.B — Handling the raw response returned from XAI
        # The format of `content` may vary, so we branch based on its type.

        if isinstance(content, list):
            # ✅ Case 1: Already a parsed list of tracks (e.g. from test mode or perfect XAI response)
            logger_step1b.debug("[STEP_1.B] ➤ content is a list — using as-is")
            logger_step1b.debug(f"[XAI] Received {len(content)} tracks.")
            tracks = content

        elif isinstance(content, str):
            # 🧾 Case 2: content is a raw JSON string (most common XAI format)
            # Needs parsing — this will be handled in STEP_1.B.1 by parse_and_filter_tracks()
            logger_step1b.debug("[STEP_1.B] ➤ content is a str — attempting to parse JSON string")
            tracks = parse_and_filter_tracks(content, num_tracks, is_test_mode=False)

        elif isinstance(content, dict):
            # 📦 Case 3: content is a dict — maybe from test JSON or postprocessed response
            logger_step1b.debug("[STEP_1.B] ➤ content is a dict — extracting 'tracks' key")
            logger_step1b.debug(f"[XAI] Dict keys: {list(content.keys())}")

            raw_tracks = content.get("tracks", [])

            # 🔍 Defensive check: make sure tracks field is actually a list
            if not isinstance(raw_tracks, list):
                raise ValueError("Expected 'tracks' to be a list.")

            logger_step1b.debug(f"[XAI] Extracted {len(raw_tracks)} tracks.")

            # Convert the list back into a string so it can go through the same cleanup pipeline
            tracks = parse_and_filter_tracks(json.dumps(raw_tracks), num_tracks, is_test_mode=False)

            # Log track summary if STEP_1.B or fallback STEP_1 logger is enabled
            if logger_step1b.isEnabledFor(logging.DEBUG) or logger.isEnabledFor(logging.DEBUG):
                if tracks:
                    logger_step1b.debug(
                        "🎧 [TEST] Tracks loaded from fixture:\n" + format_track_list(tracks)
                    )
                else:
                    logger_step1b.warning("⚠️ [TEST] No tracks loaded from fixture.")


        else:
            # ❌ Case 4: Unexpected format — raise an error
            logger_step1b.error(f"[STEP_1.B] ❌ content is unexpected type: {type(content)}")
            raise TypeError(f"Unexpected content type: {type(content)}")

        # ✅ Log tracks AFTER the isinstance tree
        if tracks:
            logger_step1b.info("🎧 [STEP_1.B] XAI Track summary:\n" + format_track_list(tracks))
        else:
            logger_step1b.debug("⚠️ No tracks returned.")

    valid_tracks = validate_tracks(tracks)
    if logger_step1c.isEnabledFor(logging.DEBUG):
        logger_step1c.debug("🎧 [STEP_1.C] Final validated track summary:\n" + format_track_list(valid_tracks))

    logger_step1c.debug(f"[STEP_1.C] [CLEANUP] {len(valid_tracks)} valid tracks from {len(tracks)} total, returning {len(valid_tracks)} cleaned from {total_requested} requested.")

    return {
        "language": language,
        "decade": decade,
        "genre": genre,
        "tracks": valid_tracks
    }

