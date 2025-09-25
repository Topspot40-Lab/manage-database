from __future__ import annotations
import asyncio
from backend.config.volume import (
    PLAY_FULL_TRACK,
    TRACK_PLAY_SECONDS as CFG_TRACK_PLAY_SECONDS,
    FULL_TRACK_FALLBACK_SECONDS,
    MAX_FULL_TRACK_SECONDS,
)

def compute_play_seconds(track) -> int:
    """
    Decide how long to let Spotify play before we move on,
    using the controls from backend/config/volume.py.
    """
    try:
        if PLAY_FULL_TRACK:
            ms = getattr(track, "duration_ms", None)
            secs = (ms / 1000.0) if ms else float(FULL_TRACK_FALLBACK_SECONDS)
            secs = min(secs, float(MAX_FULL_TRACK_SECONDS))
        else:
            secs = float(CFG_TRACK_PLAY_SECONDS)
        return max(1, int(round(secs)))
    except Exception:
        return max(1, int(round(float(CFG_TRACK_PLAY_SECONDS))))

async def sleep_with_skip(skip_event, total_seconds: int, chunk: float = 0.2) -> bool:
    """
    Cooperative sleep that returns early if skip_event is set.
    Returns True if a skip was triggered, False if completed.
    """
    remaining = float(total_seconds)
    while remaining > 0:
        if skip_event.is_set():
            skip_event.clear()
            return True
        to_sleep = chunk if remaining > chunk else remaining
        await asyncio.sleep(to_sleep)
        remaining -= to_sleep
    return False
