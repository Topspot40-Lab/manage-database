# backend/services/spotify/play_track.py

import logging
from backend.services.spotify.spotify_client import sp  # Spotipy client instance

logger = logging.getLogger("SPOTIFY_PLAY")

def play_spotify_track(track_id: str) -> bool:
    """
    Attempt to play a track on Spotify given a valid Spotify track ID.
    """
    try:
        uri = f"spotify:track:{track_id}"
        logger.info(f"🎵 Attempting to play track: {uri}")
        sp.start_playback(uris=[uri])
        return True
    except Exception as e:
        logger.error(f"❌ Failed to play track {track_id}: {e}")
        return False
