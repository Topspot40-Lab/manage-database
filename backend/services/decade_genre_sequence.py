from __future__ import annotations

import asyncio
import logging
from typing import Literal

from backend.services.decade_genre_loader import load_decade_genre_rows
from backend.services.playback_ordering import order_rows_for_mode
from backend.services.spotify.playback import play_spotify_track

from backend.services.radio_runtime import (
    log_header_and_texts,
    build_intro_jobs,
    narration_keys_for,
    play_narrations,
    play_track_with_skip,
    _ensure_volume_ok,
)

from backend.state.playback_state import (
    status,
    mark_playing,
    mark_stopped,
    update_phase,
)

from backend.config.volume import PLAY_FULL_TRACK

logger = logging.getLogger(__name__)


async def _wait_if_paused() -> None:
    """Cooperative pause loop driven by playback_state.status."""
    while getattr(status, "is_paused", False):
        await asyncio.sleep(0.25)


def _is_cancelled_or_stopped() -> bool:
    """
    Minimal cancel/stop policy:
      - Treat 'stopped' as cancelled for sequences.
      - If you later add status.cancel_requested, include it here too.
    """
    if getattr(status, "stopped", False):
        return True
    if getattr(status, "cancel_requested", False):
        return True
    return False


# ─────────────────────────────────────────────
# MAIN SEQUENCE ENGINE (DECADE / GENRE)
# ─────────────────────────────────────────────
async def run_decade_genre_sequence(
    *,
    decade: str,
    genre: str,
    start_rank: int,
    end_rank: int,
    mode: Literal["count_up", "count_down", "random"],
    tts_language: str,
    play_intro: bool,
    play_detail: bool,
    play_artist_description: bool,
    play_track: bool,
    text_intro: bool,
    text_detail: bool,
    text_artist_description: bool,
    voice_style: Literal["before", "over"] = "before",
) -> None:
    """
    Core decade/genre playback pipeline.

    - Loads ranked tracks
    - Orders by playback mode
    - Plays narration + track per entry
    - State-driven via backend.state.playback_state (no _flags)
    """

    logger.info(
        "🎧 Starting sequence: %s/%s %d-%d mode=%s lang=%s voice=%s",
        decade,
        genre,
        start_rank,
        end_rank,
        mode,
        tts_language,
        voice_style,
    )

    mark_playing(
        mode="decade_genre",
        language=tts_language,
        context={
            "decade": decade,
            "genre": genre,
            "start_rank": start_rank,
            "end_rank": end_rank,
            "order": mode,
        },
    )

    try:
        rows = load_decade_genre_rows(
            decade=decade,
            genre=genre,
            start_rank=start_rank,
            end_rank=end_rank,
        )

        if not rows:
            logger.warning("⚠️ No tracks found for %s/%s", decade, genre)
            return

        rows = order_rows_for_mode(rows, mode)

        for track, artist, tr_rank, decade_obj, genre_obj in rows:

            if _is_cancelled_or_stopped():
                logger.info("🛑 Sequence cancelled/stopped before rank #%02d", tr_rank.ranking)
                break

            await _wait_if_paused()

            rank = tr_rank.ranking
            logger.info("▶ Rank #%02d: %s — %s", rank, track.track_name, artist.artist_name)

            update_phase(
                "prelude",
                is_playing=True,
                context={
                    "rank": rank,
                    "track_name": track.track_name,
                    "artist_name": artist.artist_name,
                    "decade": decade,
                    "genre": genre,
                    "voice_style": voice_style,
                },
            )

            # Logging + localization
            log_header_and_texts(
                lang=tts_language,
                track=track,
                artist=artist,
                tr_rows=[(tr_rank, decade_obj.decade_name, genre_obj.genre_name)],
            )

            intro_jobs = build_intro_jobs(
                lang=tts_language,
                tr_rows=[(tr_rank, decade_obj.decade_name, genre_obj.genre_name)],
            )

            detail_bucket, detail_key, artist_bucket, artist_key = narration_keys_for(
                lang=tts_language,
                track=track,
                artist=artist,
            )

            # ─────────── VOICE STYLE: OVER TRACK ───────────
            if voice_style == "over" and play_track and track.spotify_track_id:
                logger.info("🎧 OVER mode — starting track before narration")
                await _ensure_volume_ok()
                play_spotify_track(track.spotify_track_id)
                await asyncio.sleep(0.4)

                await play_narrations(
                    play_intro=play_intro,
                    play_detail=play_detail,
                    play_artist=play_artist_description,
                    intro_jobs=intro_jobs,
                    detail_bucket=detail_bucket,
                    detail_key=detail_key,
                    artist_bucket=artist_bucket,
                    artist_key=artist_key,
                    lang=tts_language,
                    mode="decade_genre",
                    rank=rank,
                    track_name=track.track_name,
                    artist_name=artist.artist_name,
                    voice_style="over",
                )

                skipped = await play_track_with_skip(
                    track=track,
                    lang=tts_language,
                    mode="decade_genre",
                    rank=rank,
                    track_name=track.track_name,
                    artist_name=artist.artist_name,
                    full_flag=PLAY_FULL_TRACK,
                    already_playing=True,
                )

                if skipped:
                    logger.info("⏭️ Track skipped — continuing")
                    continue

            # ─────────── VOICE STYLE: BEFORE TRACK ───────────
            else:
                await play_narrations(
                    play_intro=play_intro,
                    play_detail=play_detail,
                    play_artist=play_artist_description,
                    intro_jobs=intro_jobs,
                    detail_bucket=detail_bucket,
                    detail_key=detail_key,
                    artist_bucket=artist_bucket,
                    artist_key=artist_key,
                    lang=tts_language,
                    mode="decade_genre",
                    rank=rank,
                    track_name=track.track_name,
                    artist_name=artist.artist_name,
                    voice_style="before",
                )

                if play_track:
                    skipped = await play_track_with_skip(
                        track=track,
                        lang=tts_language,
                        mode="decade_genre",
                        rank=rank,
                        track_name=track.track_name,
                        artist_name=artist.artist_name,
                        full_flag=PLAY_FULL_TRACK,
                        already_playing=False,
                    )

                    if skipped:
                        logger.info("⏭️ Track skipped — continuing")
                        continue

            await _wait_if_paused()
            await asyncio.sleep(0.4)

        logger.info("🎉 Sequence finished: %s / %s", decade, genre)

    except asyncio.CancelledError:
        logger.info("⛔ Sequence task cancelled")
        raise

    except Exception:
        logger.exception("⚠️ Sequence error for %s/%s", decade, genre)

    finally:
        mark_stopped()
        logger.debug("🧹 Playback state reset for %s/%s", decade, genre)
