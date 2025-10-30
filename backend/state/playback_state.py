from __future__ import annotations
import time
from typing import Literal, Optional
from pydantic import BaseModel

Phase = Literal["idle", "intro", "detail", "artist", "track"]
Mode  = Literal["decade_genre", "collection"]

class PlaybackStatus(BaseModel):
    is_playing: bool = False
    is_paused: bool = False
    stopped: bool = False
    language: str = "en"
    mode: Mode | None = None
    context: dict = {}
    current_rank: Optional[int] = None
    phase: Phase = "idle"
    last_action_ts: float = time.time()

status = PlaybackStatus()

def update_phase(phase: Phase, **kwargs) -> None:
    status.phase = phase
    for k, v in kwargs.items():
        setattr(status, k, v)
    status.last_action_ts = time.time()

def mark_playing(mode: Mode, lang: str) -> None:
    status.is_playing = True
    status.is_paused = False
    status.stopped = False
    status.mode = mode
    status.language = lang
    status.last_action_ts = time.time()

def mark_paused() -> None:
    status.is_playing = False
    status.is_paused = True
    status.last_action_ts = time.time()

def mark_stopped() -> None:
    status.is_playing = False
    status.is_paused = False
    status.stopped = True
    status.phase = "idle"
    status.last_action_ts = time.time()
