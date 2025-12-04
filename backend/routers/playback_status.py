from fastapi import APIRouter
from backend.routers.playback_control import _flags
import time

router = APIRouter(prefix="/playback", tags=["Playback Status"])

# Timestamp for last track start
_last_start_time = None


@router.get("/status")
async def get_status():
    """
    Returns:
      {
        phase: "track",
        durationMs: 182000,
        elapsedMs: 54000,
        track_name: "...",
        artist_name: "...",
        rank: 7
      }
    """
    ctx = getattr(_flags, "context", {}) or {}

    if not ctx:
        return {"phase": "idle"}

    duration = ctx.get("durationMs") or 0

    # If track is playing, compute elapsed
    global _last_start_time
    if ctx.get("phase") == "track" and getattr(_flags, "is_playing", False):
        if _last_start_time is None:
            _last_start_time = time.time()

        elapsed_ms = int((time.time() - _last_start_time) * 1000)
    else:
        elapsed_ms = 0
        _last_start_time = None

    return {
        **ctx,
        "elapsedMs": elapsed_ms,
        "durationMs": duration,
    }
