import logging
from backend.services.spotify.spotify_auth_user import get_spotify_user_client
from spotipy.exceptions import SpotifyException

logger = logging.getLogger(__name__)


def play_spotify_track(track_id: str) -> bool:
    try:
        sp = get_spotify_user_client()

        # 🔍 Step 1: Check active devices
        devices = sp.devices().get("devices", [])
        if not devices:
            logger.error("❌ No active Spotify devices found. Open Spotify and play something first.")
            return False

        # Log active device list
        logger.info("🎧 Active Spotify devices:")
        for d in devices:
            logger.info(f"  • {d['name']} — type: {d['type']} — active: {d['is_active']} — id: {d['id']}")

        # Optional: Pick the active device (if needed)
        active_device = next((d for d in devices if d["is_active"]), None)
        if not active_device:
            logger.warning("⚠️ No device is currently marked as active — Spotify may not play the track.")

        # 🔁 Step 2: Try to start playback
        uri = f"spotify:track:{track_id}"
        sp.start_playback(uris=[uri])
        logger.info(f"▶️ Started playback for track: {track_id}")
        return True

    except SpotifyException as e:
        logger.error(f"⚠️ Spotify API error: {e.msg}")
        return False
    except Exception as e:
        logger.error(f"⚠️ Unexpected playback error for track {track_id}: {e}")
        return False
