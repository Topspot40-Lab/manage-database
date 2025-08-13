# backend/services/spotify/playback.py
import logging
from spotipy.exceptions import SpotifyException
from backend.services.spotify.spotify_auth_user import get_spotify_user_client

logger = logging.getLogger(__name__)

def play_spotify_track(track_id: str) -> bool:
    """
    Start playback of a single Spotify track on the active device.

    Returns True if the start_playback call was issued successfully, False otherwise.
    """
    try:
        sp = get_spotify_user_client()

        # 1) Check active devices
        devices = sp.devices().get("devices", [])
        if not devices:
            logger.error("❌ No active Spotify devices found. Open Spotify on a device first.")
            return False

        logger.debug("🎧 Active Spotify devices:")
        for d in devices:
            logger.debug(f"  • {d['name']} — type: {d['type']} — active: {d['is_active']} — id: {d['id']}")

        # Prefer an active device if present (not strictly required to pass device_id for start_playback)
        active_device = next((d for d in devices if d.get("is_active")), None)
        if not active_device:
            logger.warning("⚠️ No device currently marked as active — Spotify may not play the track until a device is active.")

        # 2) Start playback
        uri = f"spotify:track:{track_id}"
        sp.start_playback(uris=[uri])
        logger.debug(f"▶️ Started playback for track: {track_id}")
        return True

    except SpotifyException as e:
        logger.error(f"⚠️ Spotify API error: {e.msg}")
        return False
    except Exception as e:
        logger.error(f"⚠️ Unexpected playback error for track {track_id}: {e}")
        return False
