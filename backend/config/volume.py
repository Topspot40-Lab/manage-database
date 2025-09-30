# backend/config/volume.py
from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# MASTER PLAYBACK CONTROLS  (edit these values directly)
# ─────────────────────────────────────────────────────────────────────────────

# Per-narration gain in decibels (negative = quieter)
INTRO_GAIN_DB:  float = -6.0
DETAIL_GAIN_DB: float = 0.0
ARTIST_GAIN_DB: float = 0.0

# Spotify/device volumes (percent 0..100)
# MAIN controls the primary output (e.g., music).
MAIN_VOLUME_PERCENT: int = 40

# BED (background/bed track) volume:
# Option A) fixed percentage below (uncomment & set BED_FACTOR=None)
BED_VOLUME_PERCENT: int = 20

# Option B) compute from MAIN via factor (set to a number like 0.3; else None)
BED_FACTOR: float | None = None  # e.g., 0.3 → 30% of MAIN

# Bed crossfade time in milliseconds
BED_FADE_MS: int = 1200

# ─────────────────────────────────────────────────────────────────────────────
# TRACK PLAY LENGTH CONTROLS
# ─────────────────────────────────────────────────────────────────────────────

# If True → try to play the full track. If False → play fixed number of seconds.
PLAY_FULL_TRACK: bool = False

# Used when PLAY_FULL_TRACK is False (or a request explicitly sets full=False)
TRACK_PLAY_SECONDS: int = 30

# If PLAY_FULL_TRACK is True but we don't have a duration on the Track model,
# use this fallback number of seconds.
FULL_TRACK_FALLBACK_SECONDS: int = 180  # 3 minutes

# Safety cap so "full" never blocks forever (e.g., 15 minutes max)
MAX_FULL_TRACK_SECONDS: int = 900

# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL HELPERS (no need to edit below)
# ─────────────────────────────────────────────────────────────────────────────

def _clamp(v: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, v))

# Compute the effective BED volume from MAIN and/or factor
if BED_FACTOR is not None:
    BED_VOLUME_PERCENT = _clamp(int(round(MAIN_VOLUME_PERCENT * BED_FACTOR)))
else:
    BED_VOLUME_PERCENT = _clamp(BED_VOLUME_PERCENT)

def resolve_track_sleep_seconds(
    *,
    play_full: bool | None = None,
    seconds_override: int | None = None,
    track_duration_ms: int | None = None,
) -> int:
    """
    Decide how long to sleep after starting Spotify:
    - If play_full is True (or default): use track_duration_ms if available,
      else FULL_TRACK_FALLBACK_SECONDS. Clamp to MAX_FULL_TRACK_SECONDS.
    - If play_full is False: use seconds_override if provided, else TRACK_PLAY_SECONDS.
    Returns seconds (int, >= 0).
    """
    pf = PLAY_FULL_TRACK if play_full is None else bool(play_full)
    if pf:
        if track_duration_ms and track_duration_ms > 0:
            secs = int(round(track_duration_ms / 1000.0))
        else:
            secs = int(FULL_TRACK_FALLBACK_SECONDS)
        return max(0, min(secs, int(MAX_FULL_TRACK_SECONDS)))
    else:
        secs = seconds_override if (seconds_override is not None and seconds_override >= 0) else TRACK_PLAY_SECONDS
        return max(0, int(secs))
