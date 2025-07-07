# ─────────────────────────────────────────────────────────────────────────────
# 📦 Imports
# ─────────────────────────────────────────────────────────────────────────────
from enum import IntEnum
from typing import Optional

from backend.utils.json_helpers import (
    parse_featured_artists,
    normalize_name,
    get_mode_flag
)
from backend.utils.mode_utils import ModeFlag


# ─────────────────────────────────────────────────────────────────────────────
# 🗺️ Key Mapping & Validation Rules
# ─────────────────────────────────────────────────────────────────────────────
TRACK_KEY_MAP = {
    "trackName": "track_name",
    "track_name": "track_name",
    "artistName": "artist_name",
    "artist_name": "artist_name",
    "yearReleased": "year_released",
    "year_released": "year_released",
    "rank": "rank",
    "intro": "intro",
    "detail": "detail"
}

REQUIRED_KEYS = [
    "track_name",
    "artist_name",
    "year_released",
    "rank"
]


# ─────────────────────────────────────────────────────────────────────────────
# 🧹 Normalize Track Keys
# ─────────────────────────────────────────────────────────────────────────────
def normalize_track_keys(base: dict, logger) -> dict:
    """
    Normalize raw track dictionary keys from camelCase to snake_case.
    Logs skipped keys and warns about missing required keys.
    """
    result = {}

    for key, value in base.items():
        normalized_key = TRACK_KEY_MAP.get(key)
        if normalized_key:
            result[normalized_key] = value
        else:
            logger.debug(f"🧹 [normalize_track_keys] Skipping unrecognized key: '{key}'")

    logger.debug(f"✅ [normalize_track_keys] Normalized keys: {list(result.keys())}")

    # Check for missing required keys
    missing = [k for k in REQUIRED_KEYS if k not in result]
    if missing:
        logger.warning(f"⚠️ [normalize_track_keys] Missing required keys: {missing}")

    return result


# ─────────────────────────────────────────────────────────────────────────────
# 🗣️ TTS-Friendly Artist Mode Phrases
# ─────────────────────────────────────────────────────────────────────────────
def get_mode_flag_detail_for_tts(track: dict) -> Optional[str]:
    """
    Returns a TTS-friendly phrase for the artist's mode:
    - "in a duet with X"
    - "featuring Y"
    - "performed by the group Z"
    Returns None for solo artists.
    """
    mode = track.get("mode_flag")
    main = track.get("main_artist_name", "")
    feat = track.get("featured_artist_name", "")

    if mode == ModeFlag.SOLO:
        return None
    elif mode == ModeFlag.DUET and feat:
        return f"in a duet with {feat}"
    elif mode == ModeFlag.FEATURED and feat:
        return f"featuring {feat}"
    elif mode == ModeFlag.GROUP:
        return f"performed by the group {main}"
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 🧠 Set Mode Flag, Display Name, and TTS Detail
# ─────────────────────────────────────────────────────────────────────────────
def set_mode_fields(track: dict, logger) -> dict:
    """
    Given a track with raw artist_name, determine:
    - mode_flag (solo, duet, featured, group)
    - main and featured artist names
    - display name (for UI)
    - mode_flag_detail (for TTS)
    """
    artist_name_raw = track.get("artist_name", "").strip()
    logger.debug(f"🎭 [set_mode_fields] Parsing artist_name: '{artist_name_raw}'")

    # Extract artist parts
    main_raw, feat_raw, keyword = parse_featured_artists(artist_name_raw)

    # Normalize for mode logic
    main = normalize_name(main_raw)
    feat = normalize_name(feat_raw) if feat_raw else None

    logger.debug(f"🔍 Checking mode_flag for main='{main}', feat='{feat}', keyword='{keyword}'")
    mode_str = get_mode_flag(main, feat, keyword)

    # Determine display name and enum
    if mode_str == "duet":
        display = f"{main_raw} and {feat_raw}"
        mode_enum = ModeFlag.DUET
    elif mode_str == "featured":
        display = f"{main_raw} feat. {feat_raw}"
        mode_enum = ModeFlag.FEATURED
    elif mode_str == "group":
        display = artist_name_raw
        mode_enum = ModeFlag.GROUP
    else:
        display = main_raw
        mode_enum = ModeFlag.SOLO

    # Final field assignment
    track["main_artist_name"] = main_raw
    track["featured_artist_name"] = feat_raw
    track["artist_display_name"] = display
    track["mode_flag"] = mode_enum.value
    track["mode_label"] = mode_enum.name
    track["mode_flag_detail"] = get_mode_flag_detail_for_tts(track)

    print(f"🗣️ mode_flag_detail (for TTS): '{track['mode_flag_detail']}'")

    # logger_step1b.debug(f"✅ mode_flag: {mode_enum.name}, display: '{display}'")
    # logger_step1b.debug(f"🗣️ mode_flag_detail (for TTS): '{track['mode_flag_detail']}'")

    return track
