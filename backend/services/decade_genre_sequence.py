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
    _update_flags,
    _respect_user_controls,
    play_track_with_skip,
    _ensure_volume_ok,
)

from backend.routers.playback_control import _flags
from backend.config.volume import PLAY_FULL_TRACK

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# MAIN SEQUENCE ENGINE (RUNS FULL RANGE)
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

    - Loads all tracks for (decade, genre, rank-range)
    - Orders by mode (count_up / count_down / random)
    - For each track:
        * Updates playback flags
        * Runs narration (before/over)
        * Runs Spotify playback with skip support
    """

    logger.info(
        "🎧 Starting sequence: %s/%s %d-%d mode=%s lang=%s voice_style=%s",
        decade,
        genre,
        start_rank,
        end_rank,
        mode,
        tts_language,
        voice_style,
    )

    # ─────────── Reset playback flags ───────────
    _flags.cancel_requested = False
    _flags.is_playing = True
    _flags.mode = "decade_genre"
    _flags.playback_order = mode
    _flags.decade = decade
    _flags.genre = genre
    _flags.language = tts_language

    _flags.context = {
        "decade": decade,
        "genre": genre,
        "start_rank": start_rank,
        "end_rank": end_rank,
    }

    try:
        # ─────────── DB QUERY ───────────
        logger.warning(
            "🔎 QUERY INPUT → decade=%s | genre=%s | start=%s | end=%s",
            decade,
            genre,
            start_rank,
            end_rank,
        )

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

        # ─────────── MAIN LOOP ───────────
        for track, artist, tr_rank, decade_obj, genre_obj in rows:

            if getattr(_flags, "cancel_requested", False):
                logger.info("🛑 Sequence cancelled before rank #%02d.", tr_rank.ranking)
                break

            rank = tr_rank.ranking

            logger.info(
                "▶ Rank #%02d: %s — %s",
                rank,
                track.track_name,
                artist.artist_name,
            )

            _update_flags(
                phase="prelude",
                lang=tts_language,
                mode="decade_genre",
                rank=rank,
                track_name=track.track_name,
                artist_name=artist.artist_name,
            )

            await _respect_user_controls()

            # ─────────── Narration Prep ───────────
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

            # ─────────── VOICE STYLE ───────────
            if voice_style == "over" and play_track and track.spotify_track_id:
                logger.info("🎧 OVER-TRACK: starting main track before narration.")
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
                    logger.info("⏭️ Track skipped — continuing.")
                    continue

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
                        logger.info("⏭️ Track skipped — continuing.")
                        continue

            await _respect_user_controls()
            await asyncio.sleep(0.5)

        logger.info("🎉 Sequence finished (decade/genre %s/%s).", decade, genre)

    except asyncio.CancelledError:
        logger.info("⛔ Sequence task cancelled.")
        raise

    except Exception as e:
        logger.warning("⚠️ Sequence error for %s/%s: %s", decade, genre, e)

    finally:
        _flags.is_playing = False
        _flags.cancel_requested = False
        _flags.context = {"decade": decade, "genre": genre}
        logger.debug("🧹 Sequence flags reset for %s/%s", decade, genre)
