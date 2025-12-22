from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional, Literal

Phase = Literal["idle", "intro", "detail", "artist", "track", "ended", "music"]
Mode  = Literal["decade_genre", "collection"]

@dataclass
class PlaybackStatus:
    # Core flags
    is_playing: bool = False
    is_paused: bool = False
    stopped: bool = True
    cancel_requested: bool = False

    # Context
    language: str = "en"
    mode: Optional[Mode] = None
    context: dict[str, Any] = field(default_factory=dict)
    current_rank: Optional[int] = None

    # UI progress
    elapsed_seconds: float = 0.0
    duration_seconds: float = 0.0
    percent_complete: float = 0.0

    # Phase + labels
    phase: Phase = "idle"
    track_name: str = ""
    artist_name: str = ""

    # Timing
    last_action_ts: float = field(default_factory=time.time)


# 🔴 SINGLE GLOBAL INSTANCE (this replaces `_flags`)
status = PlaybackStatus()


# ─────────────────────────────────────────────
# Helpers (small, explicit, boring = good)
# ─────────────────────────────────────────────
def _touch() -> None:
    status.last_action_ts = time.time()


def update_phase(phase: Phase, **kwargs) -> None:
    status.phase = phase
    for k, v in kwargs.items():
        setattr(status, k, v)
    _touch()


def mark_playing(
    *,
    mode: Mode,
    language: str,
    context: Optional[dict[str, Any]] = None,
) -> None:
    status.is_playing = True
    status.is_paused = False
    status.stopped = False
    status.mode = mode
    status.language = language
    if context is not None:
        status.context = context
    _touch()


def mark_paused() -> None:
    status.is_playing = False
    status.is_paused = True
    _touch()


def mark_stopped() -> None:
    status.is_playing = False
    status.is_paused = False
    status.stopped = True
    status.cancel_requested = False
    status.phase = "idle"
    status.elapsed_seconds = 0.0
    status.duration_seconds = 0.0
    status.percent_complete = 0.0
    _touch()
