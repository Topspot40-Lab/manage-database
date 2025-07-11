# ─────────────────────────────────────────────────────────────────────────────
# 📦 Imports
# ─────────────────────────────────────────────────────────────────────────────
from typing import Optional

from backend.utils.json_helpers import (
    parse_featured_artists,
    normalize_name,
    get_mode_flag
)
from backend.utils.mode_utils import ModeFlag

print(">>> 🧙 set_mode_fields loaded fresh <<<")

# ─────────────────────────────────────────────────────────────────────────────
# 🗺️ Key Mapping & Validation Rules
# ─────────────────────────────────────────────────────────────────────────────
TRACK_KEY_MAP = {
    "trackName": "track_name",
    "track_name": "track_name",
    "artistName": "artist_name",
    "artist_name": "artist_name",
    "artistDisplayName": "artist_display_name",          # ✅ NEW
    "featuredArtistName": "featured_artist_name",        # ✅ NEW
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
    Normalize a raw track dictionary by converting key names to consistent snake_case.
    Preserves enriched metadata by favoring non-null values if duplicates are found.
    """
    result = {}

    for key, value in base.items():
        normalized_key = TRACK_KEY_MAP.get(key)

        if normalized_key:
            if normalized_key in result:
                existing = result[normalized_key]
                if existing in [None, "", []] and value not in [None, "", []]:
                    logger.debug(f"🔁 Overwriting '{normalized_key}' null/empty value with enriched value.")
                    result[normalized_key] = value
                else:
                    logger.debug(f"⚠️ Skipping '{normalized_key}'; existing value is non-empty.")
            else:
                result[normalized_key] = value
        else:
            # Keep unknown or already-normalized keys (like spotify_data, artist_artwork, etc.)
            if key not in result:
                result[key] = value
            else:
                logger.debug(f"⚠️ normalize_track_keys: Skipping unknown key '{key}' already in result.")

    return result


# ─────────────────────────────────────────────────────────────────────────────
# 🗣️ TTS-Friendly Artist Mode Phrases
# ─────────────────────────────────────────────────────────────────────────────
import random

def get_mode_flag_detail_for_tts(track: dict) -> Optional[str]:
    """
    Returns a TTS-friendly phrase for the artist's mode:
    - Duet: varied phrasing like "in a duet with", "joined by"
    - Featured: varied phrasing like "featuring", "with special guest"
    - Group: varied phrasing like "performed by the group", "from the band"
    Returns None for solo artists.
    """
    mode = track.get("mode_flag")
    main = track.get("main_artist_name", "")
    feat = track.get("featured_artist_name", "")

    if mode == ModeFlag.SOLO:
        return None

    elif mode == ModeFlag.DUET and feat:
        duet_phrases = [
            f"in a duet with {feat}",
            f"joined by {feat}",
            f"sharing the mic with {feat}",
            f"performing alongside {feat}",
            f"a two-voice harmony with {feat}"
        ]
        return random.choice(duet_phrases)

    elif mode == ModeFlag.FEATURED and feat:
        feature_phrases = [
            f"featuring {feat}",
            f"with special guest {feat}",
            f"with a spotlight on {feat}",
            f"with help from {feat}",
            f"with a featured performance by {feat}"
        ]
        return random.choice(feature_phrases)

    elif mode == ModeFlag.GROUP:
        group_phrases = [
            f"performed by the group {main}",
            f"a hit from the band {main}",
            f"recorded by country group {main}",
            f"delivered by legendary group {main}",
            f"from the classic band {main}",
            f"brought to you by {main}",
            f"created by the talented group {main}"
        ]
        return random.choice(group_phrases)

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
    # logger.debug(f"🎭 [set_mode_fields] Parsing artist_name: '{artist_name_raw}'")

    # Extract artist parts
    main_raw, feat_raw, keyword = parse_featured_artists(artist_name_raw)

    # Normalize for mode logic
    main = normalize_name(main_raw)
    feat = normalize_name(feat_raw) if feat_raw else None

    # logger.debug(f"🔍 Checking mode_flag for main='{main}', feat='{feat}', keyword='{keyword}'")
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
    track["artist_name"] = main
    track["main_artist_name"] = main_raw
    track["featured_artist_name"] = feat_raw
    track["artist_display_name"] = display
    track["mode_flag"] = mode_enum.value
    track["mode_label"] = mode_enum.name
    track["mode_flag_detail"] = get_mode_flag_detail_for_tts(track)

    # print(f"🗣️ mode_flag_detail (for TTS): '{track['mode_flag_detail']}'")

    # logger_step1b.debug(f"✅ mode_flag: {mode_enum.name}, display: '{display}'")
    # logger_step1b.debug(f"🗣️ mode_flag_detail (for TTS): '{track['mode_flag_detail']}'")

    return track
