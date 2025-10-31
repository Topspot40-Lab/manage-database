import asyncio
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

        # Prefer an active device if present
        active_device = next((d for d in devices if d.get("is_active")), None)
        if not active_device:
            logger.warning("⚠️ No device currently marked as active — Spotify may not play until a device is active.")
        else:
            logger.debug(f"▶ Using device: {active_device['name']} ({active_device['id']})")

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


# ─────────────────────────────────────────────
# ✨ Bed Fade-Out Helper
# ─────────────────────────────────────────────
async def stop_spotify_playback(fade_out_seconds: float = 1.5, steps: int = 10) -> None:
    """
    Gracefully fade the current Spotify playback volume to zero and pause.
    Works with the same authenticated user client.
    """
    try:
        sp = get_spotify_user_client()
        devices = sp.devices().get("devices", [])
        if not devices:
            logger.debug("No Spotify devices found — nothing to fade.")
            return

        # Pick active device or first one
        device = next((d for d in devices if d.get("is_active")), devices[0])
        device_id = device.get("id")
        logger.debug(f"🔉 Preparing to fade out on device: {device.get('name')} ({device_id})")

        # Get current volume
        pb = sp.current_playback()
        current_vol = int(pb.get("device", {}).get("volume_percent", 100)) if pb else 100

        # Fade down in steps
        steps = max(1, steps)
        delay = fade_out_seconds / steps
        decrement = max(1, current_vol // steps)

        vol = current_vol
        while vol > 0:
            vol = max(0, vol - decrement)
            try:
                sp.volume(vol, device_id=device_id)
            except Exception as e:
                logger.debug(f"Volume set failed at {vol}%: {e}")
                break
            await asyncio.sleep(max(0.05, delay))

        # Pause playback once silent
        try:
            sp.pause_playback(device_id=device_id)
            logger.info("⏸️ Bed track faded out and paused.")
        except Exception as e:
            logger.debug(f"Pause failed: {e}")

    except Exception as e:
        logger.warning(f"⚠️ stop_spotify_playback error: {e}")
