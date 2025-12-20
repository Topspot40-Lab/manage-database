from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Literal, Sequence

from backend.services.radio_runtime import (
    play_narrations,
    play_track_with_skip,
)
from backend.state.skip import skip_event
from backend.state.playback_state import update_phase
from backend.state.playback_flags import flags



logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# DATA MODELS
# ─────────────────────────────────────────────
@dataclass(frozen=True)
class TrackRef:
    track_id: int | str
    spotify_track_id: str
    rank: int
    track_name: str
    artist_name: str


@dataclass(frozen=True)
class PlaybackSelection:
    language: Literal["en", "es", "ptbr", "pt-BR"]
    voices: Sequence[Literal["intro", "detail", "artist"]]
    voicePlayMode: Literal["before", "over"]
    pauseMode: Literal["pause", "continuous"]  # TODO: hook into pause behavior


def _clear_skip():
    try:
        skip_event.clear()
    except Exception:
        pass


# ─────────────────────────────────────────────
# MAIN SINGLE-TRACK PIPELINE
# ─────────────────────────────────────────────
async def play_one_track_pipeline(
    *,
    track: TrackRef,
    selection: PlaybackSelection,
) -> None:
    """
    Real single-track playback pipeline.

    Order:
      1) Optional narration (intro / detail / artist)
      2) Spotify track playback
    """

    logger.info(
        "🎛️ Engine start: rank=%s track=%s artist=%s mode=%s voices=%s",
        track.rank,
        track.track_name,
        track.artist_name,
        selection.voicePlayMode,
        list(selection.voices),
    )

    _clear_skip()

    # 🚨 CRITICAL: clear cancel/stop flags before playback
    flags.cancel_requested = False
    flags.stopped = False
    logger.info("🔄 Playback flags cleared before playback start")

    # ─────────────────────────────────────────────
    # PHASE 1: NARRATION (if any)
    # ─────────────────────────────────────────────
    if selection.voices:
        try:
            await play_narrations(
                play_intro="intro" in selection.voices,
                play_detail="detail" in selection.voices,
                play_artist="artist" in selection.voices,
                intro_jobs=[],          # single-track mode: no ranking-based intro
                detail_bucket=None,
                detail_key=None,
                artist_bucket=None,
                artist_key=None,
                lang=selection.language,
                mode="single",
                rank=track.rank,
                track_name=track.track_name,
                artist_name=track.artist_name,
                voice_style=selection.voicePlayMode,
            )
        except asyncio.CancelledError:
            logger.info("🛑 Narration cancelled.")
            update_phase("ended", current_rank=track.rank)
            return

    # ─────────────────────────────────────────────
    # PHASE 2: TRACK PLAYBACK
    # ─────────────────────────────────────────────
    try:
        skipped = await play_track_with_skip(
            track,
            lang=selection.language,
            mode="single",
            rank=track.rank,
            track_name=track.track_name,
            artist_name=track.artist_name,
            already_playing=(selection.voicePlayMode == "over"),
        )

        if skipped:
            logger.info("⏭️ Track skipped.")
        else:
            logger.info("✅ Track finished normally.")

    except asyncio.CancelledError:
        logger.info("🛑 Track playback cancelled.")
        update_phase("ended", current_rank=track.rank)
        return

    # ─────────────────────────────────────────────
    # DONE
    # ─────────────────────────────────────────────
    update_phase("ended", current_rank=track.rank)
    logger.info("🏁 Engine done: rank=%s", track.rank)
