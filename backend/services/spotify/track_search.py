# backend/services/spotify/track_search.py

from typing import Optional
from spotipy import Spotify
from spotipy.oauth2 import SpotifyClientCredentials
from backend.utils.logger_factory import get_step_logger

logger = get_step_logger("STEP_4.D")

# 🔑 One-time Spotify client setup
sp = Spotify(auth_manager=SpotifyClientCredentials())

def get_spotify_artist_info(artist_name: str) -> Optional[dict]:
    """
    Look up a Spotify artist by name and return ID and artwork URL.
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

        return {
            "spotify_artist_id": artist["id"],
            "artist_artwork": artist_artwork
        }

    except Exception as e:
        logger.error(f"🔥 Spotify artist lookup failed for '{artist_name}': {e}")
        return None

def get_spotify_data(track_name: str, artist_name: str) -> Optional[dict]:
    """
    Searches Spotify for a track and artist match and returns metadata.
    """
    try:
        logger.debug(f"🔎 Searching Spotify for: track:'{track_name}' artist:'{artist_name}'")
        results = sp.search(q=f"track:{track_name} artist:{artist_name}", type="track", limit=1)
        items = results.get("tracks", {}).get("items", [])
        if not items:
            logger.warning(f"❌ No Spotify track match for '{track_name}' by '{artist_name}'")
            return None

        track = items[0]
        album = track["album"]
        artist_id = track["artists"][0]["id"]
        artist_artwork = get_artist_artwork(artist_id)

        return {
            "spotify_track_id": track["id"],
            "artist_id": artist_id,
            "duration_ms": track["duration_ms"],
            "popularity": track["popularity"],
            "album_artwork": album["images"][0]["url"] if album.get("images") else None,
            "artist_artwork": artist_artwork
        }

    except Exception as e:
        logger.error(f"🔥 Spotify search failed for '{track_name}' by '{artist_name}': {e}")
        return None


def get_artist_artwork(artist_id: str) -> Optional[str]:
    """
    Fetches artist artwork by Spotify artist ID.
    """
    try:
        artist_data = sp.artist(artist_id)
        return artist_data["images"][0]["url"] if artist_data.get("images") else None
    except Exception as e:
        logger.warning(f"⚠️ Failed to fetch artist artwork for ID {artist_id}: {e}")
        return None
