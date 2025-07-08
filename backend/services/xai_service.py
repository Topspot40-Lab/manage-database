# ─────────────────────────────────────────────────────────────────────────────
# 📦 Imports
# ─────────────────────────────────────────────────────────────────────────────
import os
import json
import logging
from typing import Optional
from dotenv import load_dotenv

from backend.config import TEST_JSON_DIR
from backend.utils.mode_utils import ModeFlag
from backend.utils.track_filters import validate_tracks
from backend.services.xai_prompt_builder import build_track_prompt
from backend.services.xai_response_handler import parse_and_filter_tracks
from backend.services.xai_api_client import fetch_xai_tracks


# ─────────────────────────────────────────────────────────────────────────────
# 🔐 Environment & Config
# ─────────────────────────────────────────────────────────────────────────────
load_dotenv()
XAI_API_KEY = os.getenv("XAI_API_KEY")
XAI_API_URL = "https://api.x.ai/v1/chat/completions"
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "../schemas/track_schema.json")

with open(SCHEMA_PATH, "r") as f:
    TRACK_SCHEMA = json.load(f)


# ─────────────────────────────────────────────────────────────────────────────
# 🪵 Logger Setup
# ─────────────────────────────────────────────────────────────────────────────
def get_step_logger(name: str, fallback: str = "STEP_1") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.level == logging.NOTSET:
        return logging.getLogger(fallback)
    return logger

logger = logging.getLogger(__name__)
logger_step1a = get_step_logger("STEP_1.A")
logger_step1b = get_step_logger("STEP_1.B")
logger_step1c = get_step_logger("STEP_1.C")
logger_step1  = get_step_logger("STEP_1")   # 🔄 fallback


# ─────────────────────────────────────────────────────────────────────────────
# 🎛️ Track Formatter Utilities
# ─────────────────────────────────────────────────────────────────────────────
def format_mode_flag(flag):
    try:
        name = ModeFlag(flag).name.lower()
    except (ValueError, AttributeError):
        name = str(flag).lower()
    return {
        "solo": " solo",
        "duet": "→→  duet",
        "featured": "→→→ feat",
        "group": "→→→→ group"
    }.get(name, f" {name[:10].strip()}")


def format_track_list(tracks, fields=("rank", "track_name", "artist_name", "mode_flag")) -> str:
    """
    Return a formatted string with aligned columns for selected track fields.
    """
    if not tracks:
        return "⚠️ No tracks to display."

    field_widths = {
        "rank": 4,
        "track_name": 40,
        "artist_name": 45,
        "mode_flag": 12,
    }

    header = " | ".join(f"{field:<{field_widths[field]}}" for field in fields)
    separator = "-" * len(header)
    lines = ["🎧 Track summary:", header, separator]

    for track in tracks:
        row = []
        for field in fields:
            value = track.get(field, "")
            if field == "mode_flag":
                value = format_mode_flag(value)
            row.append(str(value).ljust(field_widths[field])[:field_widths[field]])
        lines.append(" | ".join(row))

    return "\n".join(lines)


def format_detail_track_list(tracks) -> str:
    """
    Return a 2-section track summary:
    1. Basic artist breakdown
    2. Mode and display details
    """
    if not tracks:
        return "⚠️ No tracks to display."

    lines = []

    # Section 1: Raw Artist Assignment
    lines.append("🎧 Section 1 — Raw Artist Assignment")
    header1 = f"{'rank':<4} | {'track_name':<30} | {'main_artist_name':<25} | {'featured_artist_name':<25}"
    lines.append(header1)
    lines.append("-" * len(header1))
    for t in tracks:
        lines.append(
            f"{str(t.get('rank','')):<4} | "
            f"{str(t.get('track_name',''))[:30]:<30} | "
            f"{str(t.get('main_artist_name',''))[:25]:<25} | "
            f"{str(t.get('featured_artist_name',''))[:25]:<25}"
        )
    lines.append("")

    # Section 2: Mode & Display
    lines.append("🎧 Section 2 — Mode & Display Info")
    header2 = f"{'rank':<4} | {'artist_name':<30} | {'artist_display_name':<30} | {'mode_flag':<12} | {'mode_flag_detail':<18}"
    lines.append(header2)
    lines.append("-" * len(header2))
    for t in tracks:
        lines.append(
            f"{str(t.get('rank','')):<4} | "
            f"{str(t.get('artist_name',''))[:30]:<30} | "
            f"{str(t.get('artist_display_name',''))[:40]:<40} | "
            f"{format_mode_flag(t.get('mode_flag')):<12} | "
            f"{str(t.get('mode_flag_detail',''))[:30]:<30}"
        )

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# 🧠 XAI Track Retrieval
# ─────────────────────────────────────────────────────────────────────────────
def get_top_tracks_from_xai(decade, genre, language, num_tracks, test_file_number=0):
    buffer_size = 0 if test_file_number > 0 else max(0, round(num_tracks * 0.10))
    total_requested = num_tracks + buffer_size

    logger_step1a.debug(
        f"[STEP_1.A] test_file_number={test_file_number}, num_tracks={num_tracks}, buffer={buffer_size}, "
        f"total_requested={total_requested}, decade={decade}, genre={genre}, language={language}"
    )

    prompt = build_track_prompt(decade, genre, total_requested, language, buffer_size)
    logger_step1b.debug("[STEP_1.B] Requesting top tracks from XAI...")
    tracks = []

    if test_file_number > 0:
        test_file_path = TEST_JSON_DIR / f"json_test_file_{test_file_number}.json"
        # logger_step1b.debug(f"[STEP_1.B] [TEST] Using {test_file_path}")
        try:
            with open(test_file_path, "r", encoding="utf-8") as test_file:
                test_json = json.load(test_file)
            raw_tracks = test_json.get("tracks", [])
            # logger_step1b.debug(f"[STEP_1.B] [TEST] Loaded {len(raw_tracks)} tracks.")

            tracks = parse_and_filter_tracks(json.dumps(raw_tracks), total_requested, is_test_mode=True)

            if logger_step1b.isEnabledFor(logging.INFO) or logger_step1.isEnabledFor(logging.INFO):
                # logger_step1b.info(format_track_list(tracks))
                logger_step1b.info(format_detail_track_list(tracks))

            # Stub Spotify data for consistency
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
        content = fetch_xai_tracks(prompt, test_file_number=test_file_number)

        if isinstance(content, list):
            logger_step1b.debug("[STEP_1.B] ➤ content is a list — using as-is")
            logger_step1b.debug(f"[XAI] Received {len(content)} tracks.")
            tracks = content

        elif isinstance(content, str):
            logger_step1b.debug("[STEP_1.B] ➤ content is a str — attempting to parse JSON string")
            tracks = parse_and_filter_tracks(content, num_tracks, is_test_mode=False)

        elif isinstance(content, dict):
            logger_step1b.debug("[STEP_1.B] ➤ content is a dict — extracting 'tracks' key")
            raw_tracks = content.get("tracks", [])
            if not isinstance(raw_tracks, list):
                raise ValueError("Expected 'tracks' to be a list.")
            logger_step1b.debug(f"[XAI] Extracted {len(raw_tracks)} tracks.")
            tracks = parse_and_filter_tracks(json.dumps(raw_tracks), total_requested, is_test_mode=False)

        else:
            logger_step1b.error(f"[STEP_1.B] ❌ content is unexpected type: {type(content)}")
            raise TypeError(f"Unexpected content type: {type(content)}")

        if tracks:
            logger_step1b.info("🎧 [STEP_1.B] XAI Track summary:\n" + format_track_list(tracks))
            logger_step1b.info(format_detail_track_list(tracks))
        else:
            logger_step1b.debug("⚠️ No tracks returned.")

    # Final cleanup
    valid_tracks = validate_tracks(tracks)

    if logger_step1c.isEnabledFor(logging.DEBUG):
        logger_step1c.debug("🎧 [STEP_1.C] Final validated track summary:\n" + format_track_list(valid_tracks))

    logger_step1c.debug(
        f"[STEP_1.C] [CLEANUP] {len(valid_tracks)} valid tracks from {len(tracks)} total, "
        f"returning {len(valid_tracks)} cleaned from {total_requested} requested."
    )

    return {
        "language": language,
        "decade": decade,
        "genre": genre,
        "tracks": valid_tracks
    }
