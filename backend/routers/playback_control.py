# backend/routers/playback_control.py
from __future__ import annotations

import asyncio
import time
import logging
# 🔒 Global playback sequence lock — prevents overlapping launches
sequence_lock = asyncio.Lock()

from dataclasses import dataclass, asdict
from fastapi import APIRouter
from typing import Literal, Optional

logger = logging.getLogger(__name__)

# Try loading skip_event if available
try:
    from backend.state import skip_event  # type: ignore
except Exception:
    skip_event = None

router = APIRouter(prefix="/supabase", tags=["Supabase: Playback Control"])

# ─────────────────────────────────────────────
# Global playback flags
# ─────────────────────────────────────────────
@dataclass
class _PlayFlags:
    is_playing: bool = False
    is_paused: bool = False
    stopped: bool = True
    cancel_requested: bool = False

    language: Literal["en", "es", "ptbr", "pt-BR"] = "en"
    mode: Optional[str] = None          # "decade_genre" or "collection"
    context: Optional[dict] = None      # {decade,genre} or {collection_slug}
    current_rank: Optional[int] = None
    last_action_ts: float = 0.0

_flags = _PlayFlags()

def _touch():
    _flags.last_action_ts = time.time()


# ─────────────────────────────────────────────
# GLOBAL ASYNC TASK REFERENCE
# ─────────────────────────────────────────────
current_task: asyncio.Task | None = None


# ─────────────────────────────────────────────
# CANCEL ANY EXISTING TASK
# ─────────────────────────────────────────────
async def cancel_current_sequence():
    """
    Cancels an in-flight playback coroutine (intros, details, track, bed, etc.).
    Ensures proper async cleanup before a new sequence can begin.
    """
    global current_task

    if current_task:
        logger.warning("🛑 Cancelling existing playback sequence…")
        _flags.cancel_requested = True
        try:
            current_task.cancel()
        except Exception:
            pass
        current_task = None

    _flags.is_playing = False
    _flags.stopped = True
    _flags.is_paused = False

    # 🔥 brief delay gives radio_runtime time to unwind Spotify + narration
    await asyncio.sleep(0.15)

    _flags.cancel_requested = False


# ─────────────────────────────────────────────
# START NEW BACKGROUND TASK SAFELY
# ─────────────────────────────────────────────
async def start_new_sequence(coro):
    """
    Ensures exclusive playback launch by protecting the entire
    cancel → start sequence with a global asyncio.Lock.
    """
    async with sequence_lock:
        await cancel_current_sequence()

        global current_task
        _flags.stopped = False
        _flags.is_playing = True
        _flags.cancel_requested = False

        logger.info("🎬 Launching new playback background task…")
        current_task = asyncio.create_task(coro)
        return current_task


# ─────────────────────────────────────────────
# PUBLIC API ROUTES
# ─────────────────────────────────────────────
@router.get("/status", summary="Get current playback status")
def status():
    return asdict(_flags)


@router.post("/start", summary="Mark playback as started")
def start(
    language: Literal["en", "es", "ptbr", "pt-BR"] = "en",
    mode: Optional[str] = None,
    current_rank: Optional[int] = None,
):
    _flags.is_playing = True
    _flags.is_paused = False
    _flags.stopped = False
    _flags.language = language
    _flags.mode = mode
    _flags.current_rank = current_rank
    _touch()
    return {"ok": True, "status": asdict(_flags)}


@router.post("/pause", summary="Pause playback")
def pause():
    _flags.is_paused = True
    _flags.is_playing = False
    _touch()
    return {"ok": True, "status": asdict(_flags)}


@router.post("/resume", summary="Resume playback")
def resume():
    _flags.is_paused = False
    _flags.is_playing = True
    _touch()
    return {"ok": True, "status": asdict(_flags)}


@router.post("/stop", summary="Stop playback")
def stop():
    cancel_current_sequence()
    _touch()
    return {"ok": True, "status": asdict(_flags)}


@router.post("/skip", summary="Skip to next track")
def skip():
    if skip_event is not None:
        try:
            skip_event.set()
        except Exception:
            pass

    _touch()
    return {"ok": True, "message": "Skip signaled", "status": asdict(_flags)}
