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
    tracks = track_data.get("tracks", []) if isinstance(track_data, dict) else track_data
    total = len(tracks)

    logger.debug(f"🧠 STEP 9: Generating XAI Descriptions for {total} track(s)")
    logger.debug(f"🧪 Keys in track_data: {track_data.keys()}")
    logger.debug(f"🧪 type(track_data['track_ranking']) = {type(track_data.get('track_ranking'))}")

    if ENABLE_RANK_INTRO:
        logger.debug("🔤 Generating RANK INTRO...")
        intros = get_rank_intros_from_xai(tracks, language, decade, genre)

        track_ranking = track_data.get("track_ranking")
        if isinstance(track_ranking, list):
            logger.debug(f"📋 track_ranking found with {len(track_ranking)} rows")

            intro_map = {
                (track["spotify_track_id"], track["rank"]): track["_xai_intro"]
                for track in intros.get("tracks", [])
                if track.get("spotify_track_id") and track.get("_xai_intro")
            }

            logger.debug(f"🎯 Intro map keys: {list(intro_map.keys())}")
            logger.debug(f"🎯 Track ranking keys: {[(row.get('track_id'), row.get('rank')) for row in track_ranking]}")

            for row in track_ranking:
                key = (row.get("track_id"), row.get("rank"))
                if key in intro_map:
                    row["intro"] = intro_map[key]
                    logger.debug(f"✅ Applied intro to track_ranking rank {row['rank']}")
                else:
                    logger.warning(f"❌ No intro found for track_id={row.get('track_id')} rank={row.get('rank')}")

    if ENABLE_TRACK_DETAIL:
        logger.debug("📜 Generating TRACK DETAIL...")
        get_track_details_from_xai(tracks, language)

    if ENABLE_ARTIST_DETAIL:
        logger.debug("🎙️ Generating ARTIST DESCRIPTION...")
        get_artist_descriptions_from_xai(tracks, language)

    for t in tracks:
        t.pop("intro", None)
        t.pop("_xai_intro", None)

    return {
        "language": language,
        "decade": decade,
        "genre": genre,
        "tracks": tracks,
        "track_ranking": track_data.get("track_ranking", [])
    }
