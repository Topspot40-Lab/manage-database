# backend/services/spotify/playback.py
import asyncio
import logging
from typing import Optional

from spotipy.exceptions import SpotifyException
from backend.services.spotify.spotify_auth_user import get_spotify_user_client

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────
# Device Selection Helper
# ──────────────────────────────────────────────────────────
def _pick_device_id(sp, prefer_active: bool = True) -> Optional[str]:
    """
    Pick a Spotify device:
    - Prefer active device
    - Else fallback to first available
    """
    devices = sp.devices().get("devices", [])
    if not devices:
        return None

    if prefer_active:
        active = next((d for d in devices if d.get("is_active")), None)
        if active and active.get("id"):
            return active["id"]

    # fallback to first device
    return devices[0].get("id")


# ──────────────────────────────────────────────────────────
# TRACK PLAYBACK
# ──────────────────────────────────────────────────────────
def play_spotify_track(
    track_id: str,
    *,
    device_id: Optional[str] = None,
    start_ms: int = 0,
    prefer_active_device: bool = True,
) -> bool:
    """
    Start Spotify playback on a selected device.
    Ensures stable playback by passing device_id explicitly.
    """
    try:
        sp = get_spotify_user_client()

        devices = sp.devices().get("devices", [])
        if not devices:
            logger.error("❌ No Spotify devices found. Start Spotify on your device first.")
            return False

        logger.debug("🎧 Spotify devices available:")
        for d in devices:
            logger.debug(
                "  • %s — type=%s active=%s id=%s",
                d.get("name"),
                d.get("type"),
                d.get("is_active"),
                d.get("id"),
            )

        # Pick device
        chosen_device_id = device_id or _pick_device_id(sp, prefer_active=prefer_active_device)
        if not chosen_device_id:
            logger.error("❌ No valid Spotify device ID found.")
            return False

        uri = f"spotify:track:{track_id}"

        # Explicit device — prevents the “restart track 1” bug
        sp.start_playback(
            device_id=chosen_device_id,
            uris=[uri],
            position_ms=max(0, int(start_ms)),
        )

        logger.info("▶️ Playback started: %s on device %s", track_id, chosen_device_id)
        return True

    except SpotifyException as e:
        logger.error("⚠️ Spotify API error starting track %s: %s", track_id, getattr(e, "msg", e))
        return False
    except Exception as e:
        logger.error("⚠️ Unexpected playback error for %s: %s", track_id, e, exc_info=True)
        return False


# ──────────────────────────────────────────────────────────
# HARD STOP (for skip / next / prev)
# ──────────────────────────────────────────────────────────
def stop_spotify_track(*, device_id: Optional[str] = None) -> bool:
    """
    Immediate stop (pause) without fade — used for hard skip/next.
    """
    try:
        sp = get_spotify_user_client()

        chosen_device_id = device_id or _pick_device_id(sp, prefer_active=True)
        if not chosen_device_id:
            logger.debug("No device to stop.")
            return False

        sp.pause_playback(device_id=chosen_device_id)
        logger.info("⏸️ Spotify paused on device %s", chosen_device_id)
        return True

    except Exception as e:
        logger.warning("⚠️ stop_spotify_track error: %s", e)
        return False


# ──────────────────────────────────────────────────────────
# SOFT STOP (Fade-Out)
# ──────────────────────────────────────────────────────────
async def stop_spotify_playback(fade_out_seconds: float = 1.5, steps: int = 10) -> None:
    """
    Fade Spotify volume gradually to 0, then pause.
    For nice transitions between TTS → Music or Music → TTS.
    """
    try:
        sp = get_spotify_user_client()

        devices = sp.devices().get("devices", [])
        if not devices:
            logger.debug("No Spotify devices found — nothing to fade.")
            return

        device = next((d for d in devices if d.get("is_active")), devices[0])
        device_id = device.get("id")

        logger.debug("🔉 Fading Spotify playback on %s (%s)", device.get("name"), device_id)

        # Current volume
        pb = sp.current_playback()
        current_vol = 100
        try:
            if pb and pb.get("device"):
                current_vol = int(pb["device"].get("volume_percent") or 100)
        except Exception:
            pass

        steps = max(1, steps)
        delay = fade_out_seconds / steps
        decrement = max(1, current_vol // steps)

        vol = current_vol
        while vol > 0:
            vol = max(0, vol - decrement)
            try:
                sp.volume(vol, device_id=device_id)
            except Exception:
                break
            await asyncio.sleep(max(0.05, delay))

        try:
            sp.pause_playback(device_id=device_id)
            logger.info("⏸️ Fade-out complete.")
        except Exception:
            pass

    except Exception as e:
        logger.warning("⚠️ stop_spotify_playback error: %s", e)
