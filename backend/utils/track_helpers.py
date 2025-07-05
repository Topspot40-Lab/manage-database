import re
from enum import IntEnum

import logging

logger = logging.getLogger(__name__)

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

# test files have camel case to match xai query, but need snake case later
def normalize_track_keys(base: dict) -> dict:
    """
    Normalize a raw track dictionary by converting key names to consistent snake_case.
    Removes unrecognized fields and logs them for visibility.
    """
    result = {}
    used_keys = set()

    for key, value in base.items():
        normalized_key = TRACK_KEY_MAP.get(key)
        if normalized_key:
            if normalized_key not in result:
                result[normalized_key] = value
            used_keys.add(key)
        else:
            logger.debug(f"🧹 [normalize_track_keys] Skipping unrecognized key: '{key}'")

    return result


class ModeFlag(IntEnum):
    SOLO = 1
    DUET = 2
    FEATURED = 3
    GROUP = 4


def set_mode_fields(track: dict, logger) -> dict:
    """
    Analyzes the artist_name and sets:
    - main_artist_name
    - featured_artist_name
    - mode_flag (as integer)
    - artist_display_name
    Logs decisions using the provided logger.
    """
    artist_name = track.get("artist_name", "").strip()
    logger.debug(f"🎭 [set_mode_fields] Parsing artist_name: '{artist_name}'")

    # Default values
    main = artist_name
    feat = None
    display = artist_name
    mode = ModeFlag.SOLO

    # DUET: "Artist A with Artist B"
    if " with " in artist_name:
        main, feat = [s.strip() for s in artist_name.split(" with ", 1)]
        display = f"{main} and {feat}"
        mode = ModeFlag.DUET
        logger.debug(f"🎶 Detected DUET → Main: '{main}', Duet: '{feat}'")

    # FEATURED: "Artist A feat. Artist B"
    elif re.search(r"\bfeat\.?\b", artist_name, re.IGNORECASE):
        main, feat = [s.strip() for s in re.split(r"\bfeat\.?\b", artist_name, 1, flags=re.IGNORECASE)]
        display = f"{main} feat. {feat}"
        mode = ModeFlag.FEATURED
        logger.debug(f"🎤 Detected FEATURED → Main: '{main}', Feature: '{feat}'")

    else:
        logger.debug(f"🎙️ Detected SOLO or GROUP → Artist: '{main}'")

    # Shared assignments
    track["main_artist_name"] = main
    track["featured_artist_name"] = feat
    track["artist_display_name"] = display
    track["mode_flag"] = mode.value

    return track
