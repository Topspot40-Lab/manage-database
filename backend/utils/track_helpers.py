from enum import IntEnum
from backend.utils.json_helpers import parse_featured_artists, normalize_name, get_mode_flag


# Mapping of acceptable key aliases (camelCase → snake_case)
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

def normalize_track_keys(base: dict, logger) -> dict:
    """
    Normalize a raw track dictionary by converting key names to consistent snake_case.
    Logs skipped keys and warns about any missing required keys.
    """
    result = {}

    for key, value in base.items():
        normalized_key = TRACK_KEY_MAP.get(key)
        if normalized_key:
            if normalized_key not in result:
                result[normalized_key] = value
        else:
            logger.debug(f"🧹 [normalize_track_keys] Skipping unrecognized key: '{key}'")

    logger.debug(f"✅ [normalize_track_keys] Normalized keys: {list(result.keys())}")

    # Check for missing required keys
    missing = [k for k in REQUIRED_KEYS if k not in result]
    if missing:
        logger.warning(f"⚠️ [normalize_track_keys] Missing required keys: {missing}")

    return result


class ModeFlag(IntEnum):
    SOLO = 1
    DUET = 2
    FEATURED = 3
    GROUP = 4

from backend.utils.mode_utils import ModeFlag

def set_mode_fields(track: dict, logger) -> dict:
    artist_name_raw = track.get("artist_name", "").strip()
    logger.debug(f"🎭 [set_mode_fields] Parsing artist_name: '{artist_name_raw}'")

    # Extract parts from original (raw) name
    main_raw, feat_raw, keyword = parse_featured_artists(artist_name_raw)

    # Normalize names for comparison
    main = normalize_name(main_raw)
    feat = normalize_name(feat_raw) if feat_raw else None

    # Get mode using normalized parts
    logger.debug(f"🔍 Checking mode_flag for main='{main}', feat='{feat}', keyword='{keyword}'")
    mode_str = get_mode_flag(main, feat, keyword)

    # Build display name
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

    # Final assignment
    track["main_artist_name"] = main_raw
    track["featured_artist_name"] = feat_raw
    track["artist_display_name"] = display
    track["mode_flag"] = mode_enum.value
    track["mode_label"] = mode_enum.name

    logger.debug(f"✅ mode_flag: {mode_enum.name}, display: '{display}'")
    return track