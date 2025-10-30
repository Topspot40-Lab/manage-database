# backend/routers/playback_control.py
from __future__ import annotations

import time
from dataclasses import dataclass, asdict
from fastapi import APIRouter
from typing import Literal, Optional

# We already have skip_event in your codebase; import it if available
try:
    from backend.state import skip_event  # type: ignore
except Exception:
    skip_event = None  # graceful fallback if not present

router = APIRouter(prefix="/playback")

# Minimal in-memory controller; you can later wire these flags
# into your playback loops (sleep/policy) to honor pause/stop.
@dataclass
class _PlayFlags:
    is_playing: bool = False
    is_paused: bool = False
    stopped: bool = True
    language: Literal["en", "es", "ptbr", "pt-BR"] = "en"
    mode: Optional[str] = None          # "decade_genre" or "collection"
    context: Optional[dict] = None      # {decade,genre} or {collection_slug}
    current_rank: Optional[int] = None
    last_action_ts: float = 0.0

_flags = _PlayFlags()

def _touch():
    _flags.last_action_ts = time.time()

@router.get("/status", tags=["Playback"], summary="Get current playback status")
def status():
    return asdict(_flags)

@router.post("/start", tags=["Playback"], summary="Mark playback as started")
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

@router.post("/pause", tags=["Playback"], summary="Pause playback")
def pause():
    _flags.is_paused = True
    _flags.is_playing = False
    _touch()
    return {"ok": True, "status": asdict(_flags)}

@router.post("/resume", tags=["Playback"], summary="Resume playback")
def resume():
    _flags.is_paused = False
    _flags.is_playing = True
    _touch()
    return {"ok": True, "status": asdict(_flags)}

@router.post("/stop", tags=["Playback"], summary="Stop playback")
def stop():
    _flags.is_paused = False
    _flags.is_playing = False
    _flags.stopped = True
    _touch()
    return {"ok": True, "status": asdict(_flags)}

@router.post("/skip", tags=["Playback"], summary="Skip to next track")
def skip():
    # Signal existing backend.sleep_with_skip() loops if available
    if skip_event is not None:
        try:
            skip_event.set()
        except Exception:
            pass
    _touch()
    return {"ok": True, "message": "Skip signaled", "status": asdict(_flags)}
