# backend/routers/playback_control.py
from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from typing import Literal, Optional

from fastapi import APIRouter

# ✅ KEEP data models, but not the pipeline
from backend.services.playback_engine import (
    TrackRef,
    PlaybackSelection,
)


# ✅ shared playback state (NO circular import)
from backend.state.playback_flags import (
    flags,
    touch,
    reset_for_single_track,
)

logger = logging.getLogger(__name__)

# 🔒 Global playback sequence lock — prevents overlapping launches
sequence_lock = asyncio.Lock()

# Try loading skip_event if available
try:
    from backend.state import skip_event  # type: ignore
except Exception:
    skip_event = None


router = APIRouter(
    prefix="/playback",
    tags=["Playback"],
)

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
        flags.cancel_requested = True
        try:
            current_task.cancel()
        except Exception:
            pass
        current_task = None

    flags.is_playing = False
    flags.stopped = True
    flags.is_paused = False

    # 🔥 brief delay gives radio_runtime time to unwind Spotify + narration
    await asyncio.sleep(0.15)

    # ─────────────────────────────────────────────
    # Restore Spotify volume after cancellation
    # ─────────────────────────────────────────────
    try:
        from backend.services.spotify.playback import set_device_volume
        await set_device_volume(100)
        logger.info("🔊 Restored Spotify volume to 100% after cancel")
    except Exception as exc:
        logger.warning(f"⚠️ Failed to restore volume after cancel: {exc}")

    flags.cancel_requested = False


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
        flags.stopped = False
        flags.is_playing = True
        flags.cancel_requested = False

        logger.info("🎬 Launching new playback background task…")
        current_task = asyncio.create_task(coro)
        return current_task


# ─────────────────────────────────────────────
# PUBLIC API ROUTES
# ─────────────────────────────────────────────
@router.post("/play-track", summary="Play exactly one track via sequence engine")
async def play_track(payload: dict):
    track = TrackRef(
        track_id=payload["track"]["track_id"],
        spotify_track_id=payload["track"]["spotify_track_id"],
        rank=payload["track"]["rank"],
        track_name=payload["track"]["track_name"],
        artist_name=payload["track"]["artist_name"],
    )

    selection = PlaybackSelection(
        language=payload["selection"]["language"],
        voices=payload["selection"]["voices"],
        voicePlayMode=payload["selection"]["voicePlayMode"],
        pauseMode=payload["selection"]["pauseMode"],
    )

    context = payload.get("context")
    if not context:
        return {"ok": False, "error": "Missing playback context"}

    logger.info(
        "▶️ /playback/play-track (single-step via sequence): rank=%s mode=%s context=%s",
        track.rank,
        selection.voicePlayMode,
        context.get("type"),
    )

    await cancel_current_sequence()
    reset_for_single_track()

    # ─────────────────────────────────────────────
    # SINGLE STEP = SEQUENCE OF LENGTH 1
    # ─────────────────────────────────────────────

    if context["type"] == "decade_genre":
        from backend.services.decade_genre_sequence import run_decade_genre_sequence

        coro = run_decade_genre_sequence(
            decade=context["decade"],
            genre=context["genre"],
            start_rank=track.rank,
            end_rank=track.rank,
            mode="count_up",
            tts_language=selection.language,
            play_intro=True,
            play_detail="detail" in selection.voices,
            play_artist_description="artist" in selection.voices,
            play_track=True,
            text_intro=True,
            text_detail=False,
            text_artist_description=False,
            voice_style=selection.voicePlayMode,
        )

    elif context["type"] == "collection":
        from backend.routers.collections_player import _run_play_sequence_collection

        coro = _run_play_sequence_collection(
            collection_slug=context["collection_slug"],
            start_rank=track.rank,
            end_rank=track.rank,
            mode="count_up",
            tts_language=selection.language,
            play_intro=True,
            play_detail="detail" in selection.voices,
            play_artist_description="artist" in selection.voices,
            play_track=True,
            text_intro=True,
            text_detail=False,
            text_artist_description=False,
            voice_style=selection.voicePlayMode,
        )

    else:
        return {"ok": False, "error": "Unknown playback context type"}

    await start_new_sequence(coro)

    return {
        "ok": True,
        "rank": track.rank,
        "message": "Single-step playback started via sequence engine",
    }


@router.get("/status", summary="Get current playback status")
def status():
    return asdict(flags)


@router.post("/start", summary="Mark playback as started")
def start(
    language: Literal["en", "es", "ptbr", "pt-BR"] = "en",
    mode: Optional[str] = None,
    current_rank: Optional[int] = None,
):
    flags.is_playing = True
    flags.is_paused = False
    flags.stopped = False
    flags.language = language
    flags.mode = mode
    flags.current_rank = current_rank
    touch()
    return {"ok": True, "status": asdict(flags)}


@router.post("/pause", summary="Pause playback")
def pause():
    flags.is_paused = True
    flags.is_playing = False
    touch()
    return {"ok": True, "status": asdict(flags)}


@router.post("/resume", summary="Resume playback")
def resume():
    flags.is_paused = False
    flags.is_playing = True
    touch()
    return {"ok": True, "status": asdict(flags)}


@router.post("/stop", summary="Stop playback")
async def stop():
    await cancel_current_sequence()
    touch()
    return {"ok": True, "status": asdict(flags)}


@router.post("/skip", summary="Skip to next track")
def skip():
    if skip_event is not None:
        try:
            skip_event.set()
        except Exception:
            pass

    touch()
    return {
        "ok": True,
        "message": "Skip signaled",
        "status": asdict(flags),
    }
