# backend/services/spotify/playback.py
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from spotipy.exceptions import SpotifyException
from backend.services.spotify.spotify_auth_user import get_spotify_user_client

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# GLOBAL STATE
# ─────────────────────────────────────────────
# Ensures Spotify commands never overlap
_spotify_lock = asyncio.Lock()

# Global kill-switch used by “skip” and “stop”
stop_requested = False


# ─────────────────────────────────────────────
# INTERNAL: fetch user client safely
# ─────────────────────────────────────────────
def _client():
    try:
        return get_spotify_user_client()
    except Exception as e:
        logger.error("❌ Unable to obtain Spotify user client: %s", e)
        return None


# ─────────────────────────────────────────────
# PUBLIC: Start Track Playback
# ─────────────────────────────────────────────
def play_spotify_track(track_id: str) -> bool:
    """
    Start Spotify playback immediately.
    Does NOT block — works like fire-and-forget.
    Reset kill-switch before starting.
    """
    global stop_requested
    stop_requested = False  # reset skip/stop flag

    if not track_id:
        logger.warning("🚫 No track_id passed to play_spotify_track")
        return False

    sp = _client()
    if not sp:
        return False

    try:
        devices = sp.devices().get("devices", [])
        if not devices:
            logger.error("❌ No active Spotify device. Open Spotify somewhere!")
            return False

        active = next((d for d in devices if d.get("is_active")), devices[0])
        device_id = active.get("id")

        uri = f"spotify:track:{track_id}"
        sp.start_playback(device_id=device_id, uris=[uri])

        logger.info(f"🎵 Spotify now playing: {track_id} on device {active['name']}")
        return True

    except SpotifyException as e:
        logger.error("⚠️ Spotify API error: %s", e.msg)
        return False
    except Exception as e:
        logger.error("⚠️ Unexpected error in play_spotify_track: %s", e)
        return False


# ─────────────────────────────────────────────
# BLOCKING PLAYBACK LOOP (with skip)
# ─────────────────────────────────────────────
async def play_spotify_with_skip(track_id: str, play_secs: float) -> bool:
    """
    Play track for `play_secs` seconds OR until skip/stop is triggered.

    Returns:
        True  => skipped
        False => played full duration
    """
    global stop_requested
    stop_requested = False  # reset for this track

    if not track_id:
        logger.warning("🚫 Missing track_id in play_spotify_with_skip")
        return False

    sp = _client()
    if not sp:
        return False

    async with _spotify_lock:
        # Start playback
        ok = play_spotify_track(track_id)
        if not ok:
            return False

        # Cooperative wait
        elapsed = 0
        interval = 0.25

        while elapsed < play_secs:
            if stop_requested:
                logger.info("⏭️ Skip/stop triggered — ending track early.")
                try:
                    sp.pause_playback()
                except Exception:
                    pass
                return True

            await asyncio.sleep(interval)
            elapsed += interval

        logger.info("✅ Track playback finished normally.")
        return False


# ─────────────────────────────────────────────
# PUBLIC: Stop Playback Immediately
# ─────────────────────────────────────────────
def stop_spotify_playback():
    """
    Stop Spotify immediately.
    Used by:
      • skip
      • stop
      • switching tracks
      • ending bed track
    """
    global stop_requested
    stop_requested = True

    sp = _client()
    if not sp:
        return

    try:
        devices = sp.devices().get("devices", [])
        if devices:
            active = next((d for d in devices if d.get("is_active")), devices[0])
            sp.pause_playback(device_id=active.get("id"))
            logger.info("🛑 Spotify playback stopped.")
    except Exception as e:
        logger.warning("⚠️ stop_spotify_playback error: %s", e)
