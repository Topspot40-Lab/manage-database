from typing import Optional
from spotipy import Spotify
from spotipy.oauth2 import SpotifyClientCredentials

from backend.utils.logger_factory import get_step_logger
from backend.config import ENABLE_ARTIST_DESCRIPTION

logger = get_step_logger("STEP_4.D")

# 🔑 One-time Spotify client setup
sp = Spotify(auth_manager=SpotifyClientCredentials())
from backend.services.xai_descriptions import get_artist_description  # ✅ Add this import
def get_spotify_artist_info(artist_name: str, language: str = "English") -> Optional[dict]:
    """
    Look up a Spotify artist by name and enrich with artwork + optional description.
    """
    try:
        logger.debug(f"🔍 Looking up Spotify artist: {artist_name}")
        results = sp.search(q=f"artist:{artist_name}", type="artist", limit=1)
        items = results.get("artists", {}).get("items", [])
        if not items:
            logger.debug(f"❌ No Spotify match for artist: {artist_name}")
            return None

        artist = items[0]
        artist_artwork = artist["images"][0]["url"] if artist["images"] else None

        # 🔘 Only fetch description if enabled
        artist_description = None
        if ENABLE_ARTIST_DESCRIPTION:
            artist_description = get_artist_description(artist_name, language=language)

        return {
            "spotify_artist_id": artist["id"],
            "artist_artwork": artist_artwork,
            "artist_description": artist_description
        }

    except Exception as e:
        logger.error(f"🔥 Spotify artist lookup failed for '{artist_name}': {e}")
        return None
