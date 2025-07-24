# builders/track_builder.py

import json
import logging
import re
from backend.utils.logger_factory import get_step_logger
from backend.utils.mode_utils import ModeFlag
from backend.utils.json_helpers import (
    parse_featured_artists,
    normalize_name,
    clean_text_field,
)
from backend.services.spotify.track_search import get_spotify_artist_info

logger = logging.getLogger(__name__)
logger_step4b = get_step_logger("STEP_4.B")

def clean_fallback_id(name: str) -> str:
    base = normalize_name(name)
    base = re.sub(r"\W+", "_", base)
    base = re.sub(r"_+", "_", base)
    base = base.strip("_")
    return f"test_{base}"

def build_track_entry(base, request, spotify_data, now, is_test_mode=False):
    logger_step4b.debug(f"[build_track_entry] incoming base keys: {list(base.keys())}")

    artist_name_raw = base["artist_name"]
    track_name_raw = base["track_name"]
    year_released = base["year_released"]

    artist_name_clean, featured_artist_name_raw, _ = parse_featured_artists(artist_name_raw)
    artist_name_clean = normalize_name(artist_name_clean)
    featured_artist_name_raw = featured_artist_name_raw or base.get("featured_artist_name")

    track_name_clean = normalize_name(track_name_raw)
    track_display_name = track_name_clean
    if featured_artist_name_raw:
        track_display_name += f" (feat. {featured_artist_name_raw})"

    mode_flag_str = base.get("mode_flag", "unknown")
    try:
        mode_flag = ModeFlag(mode_flag_str)
    except ValueError:
        logger_step4b.warning(f"⚠️ Invalid mode_flag '{mode_flag_str}' — defaulting to 'unknown'")
        mode_flag = ModeFlag.UNKNOWN

    detail_cleaned = clean_text_field(base.get("detail"))

    return {
        "rank": base.get("rank"),
        "track_name": track_name_clean,
        "artist_name": artist_name_clean,
        "artist_display_name": base.get("artist_display_name", artist_name_raw),
        "featured_artist": base.get("featured_artist_name", featured_artist_name_raw),
        "featured_artist_id": spotify_data.get("featured_artist_id"),
        "track_display_name": track_display_name,
        "genre": request.genre,
        "decade": request.decade,
        "spotify_track_id": spotify_data.get("spotify_track_id"),
        "spotify_artist_id": (
            spotify_data.get("artist_id")
            or base.get("artist_id")
            or clean_fallback_id(artist_name_raw)
        ),
        "mode_flag": mode_flag.value,
        "duration_ms": spotify_data.get("duration_ms"),
        "popularity": spotify_data.get("popularity"),
        "album_artwork": spotify_data.get("album_artwork"),
        "album_name": spotify_data.get("album_name"),
        "year_released": year_released,
        "is_explicit": False,
        "created_at": now,
        "detail": detail_cleaned,
    }
