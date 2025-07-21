# backend/services/xai_descriptions.py

import logging
from backend.config import (
    ENABLE_RANK_INTRO,
    ENABLE_TRACK_DETAIL,
    ENABLE_ARTIST_DETAIL,
)

from backend.services.xai_rank_intro import get_rank_intros_from_xai
from backend.services.xai_track_detail import get_track_details_from_xai
from backend.services.xai_artist_detail import get_artist_descriptions_from_xai

logger = logging.getLogger("STEP_9")

def get_track_descriptions_from_xai(track_data, language, decade, genre):
    """
    Dispatches XAI calls to generate intro, detail, and artist_description
    fields based on config flags. Returns updated track list.
    """
    tracks = track_data if isinstance(track_data, list) else track_data.get("tracks", [])
    total = len(tracks)

    logger.debug(f"🧠 STEP 9: Generating XAI Descriptions for {total} track(s)")

    if ENABLE_RANK_INTRO:
        logger.debug("🔤 Generating RANK INTRO...")
        get_rank_intros_from_xai(tracks, language, decade, genre)

    if ENABLE_TRACK_DETAIL:
        logger.debug("📜 Generating TRACK DETAIL...")
        get_track_details_from_xai(tracks, language)

    if ENABLE_ARTIST_DETAIL:
        logger.debug("🎙️ Generating ARTIST DESCRIPTION...")
        get_artist_descriptions_from_xai(tracks, language)

    return {
        "language": language,
        "decade": decade,
        "genre": genre,
        "tracks": tracks
    }
