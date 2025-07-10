# backend/services/spotify/track_search.py

import logging
from typing import Optional
from spotipy import Spotify
from spotipy.oauth2 import SpotifyClientCredentials

from backend.utils.logger_factory import get_step_logger

logger = get_step_logger("STEP_4.D")

# 🔑 One-time Spotify client setup
sp = Spotify(auth_manager=SpotifyClientCredentials())

def get_spotify_artist_info(artist_name: str) -> Optional[dict]:
    """
    Look up a Spotify artist by name.
    Returns their ID and artwork URL if found.
    """
    try:
        logger.debug(f"🔍 Looking up Spotify artist: {artist_name}")
        results = sp.search(q=f"artist:{artist_name}", type="artist", limit=1)
        items = results.get("artists", {}).get("items", [])
        if not items:
            logger.debug(f"❌ No Spotify match for artist: {artist_name}")
            return None

        artist = items[0]
        return {
            "spotify_artist_id": artist["id"],
            "artist_artwork": artist["images"][0]["url"] if artist["images"] else None,
            "artist_description": None  # Optional: future enhancement
        }

    except Exception as e:
        logger.error(f"🔥 Spotify artist lookup failed for '{artist_name}': {e}")
        return None
