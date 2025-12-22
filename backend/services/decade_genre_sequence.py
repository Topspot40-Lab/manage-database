from __future__ import annotations

import asyncio
import logging
from typing import Literal
import time


from backend.services.decade_genre_loader import load_decade_genre_rows
from backend.services.playback_ordering import order_rows_for_mode
from backend.services.spotify.playback import play_spotify_track

# Legacy flags (still used by runtime helpers)
from backend.state.playback_flags import flags

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


# ─────────────────────────────────────────────
# PAUSE / CANCEL HELPERS
# ─────────────────────────────────────────────
async def _wait_if_paused() -> None:
    """Cooperative pause loop driven by playback_state.status."""
    while getattr(status, "is_paused", False):
        await asyncio.sleep(0.25)


def _is_cancelled_or_stopped() -> bool:
    """
    Unified cancel / stop check.

    NOTE:
    We must check BOTH playback_state (new)
    and playback_flags (legacy) because runtime helpers
    still rely on flags during Option A.
    """
    if getattr(status, "stopped", False):
        return True
    if getattr(status, "cancel_requested", False):
        return True

    if getattr(flags, "stopped", False):
        return True
    if getattr(flags, "cancel_requested", False):
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
    voice_style: Literal["before", "over"] = "before",
) -> None:

    """
    Core decade/genre playback pipeline.

    - Loads ranked tracks
    - Orders by playback mode
    - Plays narration + track per entry
    - Controlled by playback_state (primary)
    - playback_flags bridged temporarily (Option A)
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

    # ─────────── RESET PLAYBACK STATE ───────────
    status.stopped = False
    status.cancel_requested = False

    # 🔁 TEMP: Reset legacy flags (critical)
    flags.is_playing = True
    flags.stopped = False
    flags.cancel_requested = False
    flags.current_rank = start_rank
    flags.mode = "decade_genre"

    logger.info("🧭 STEP 0: pre mark_playing (status=%s flags.cancel=%s)", status,
                getattr(flags, "cancel_requested", None))

    logger.info("🧭 STEP 1: calling mark_playing()")

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

    logger.info("🧭 STEP 2: mark_playing() returned")

    try:
        # ─────────── LOAD TRACK ROWS (TRIPWIRES + TIMEOUT) ───────────
        logger.info(
            "🧨 TRIPWIRE A: calling load_decade_genre_rows(decade=%r, genre=%r, start=%d, end=%d)",
            decade,
            genre,
            start_rank,
            end_rank,
        )

        t0 = time.time()
        try:
            # load_decade_genre_rows is SYNC; run it off the event loop
            rows = await asyncio.wait_for(
                asyncio.to_thread(
                    load_decade_genre_rows,
                    decade=decade,
                    genre=genre,
                    start_rank=start_rank,
                    end_rank=end_rank,
                ),
                timeout=30.0,
            )
        except asyncio.TimeoutError:
            logger.error(
                "⏱️ TRIPWIRE A TIMEOUT: load_decade_genre_rows hung > 5s. "
                "This is almost certainly a DB/session/pool issue or a blocked query."
            )
            return

        logger.info(
            "🧨 TRIPWIRE B: load_decade_genre_rows returned %d rows in %.2fs",
            len(rows),
            time.time() - t0,
        )


        logger.info(
            "📦 Loaded %d rows for %s/%s ranks %d-%d",
            len(rows),
            decade,
            genre,
            start_rank,
            end_rank,
        )

        if not rows:
            logger.error(
                "❌ NO TRACK ROWS — decade=%s genre=%s start=%d end=%d",
                decade,
                genre,
                start_rank,
                end_rank,
            )
            return

        # Diagnostic truth log (keep this)
        logger.debug(
            "🧪 cancel state → status(stopped=%s cancel=%s) flags(stopped=%s cancel=%s)",
            status.stopped,
            status.cancel_requested,
            flags.stopped,
            flags.cancel_requested,
        )

        rows = order_rows_for_mode(rows, mode)

        # ─────────── MAIN LOOP ───────────
        for track, artist, tr_rank, decade_obj, genre_obj in rows:

            if _is_cancelled_or_stopped():
                logger.info(
                    "🛑 Sequence cancelled/stopped before rank #%02d",
                    tr_rank.ranking,
                )
                break

            await _wait_if_paused()

            rank = tr_rank.ranking
            flags.current_rank = rank

            logger.info(
                "▶ Rank #%02d: %s — %s",
                rank,
                track.track_name,
                artist.artist_name,
            )

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

            # ─────────── NARRATION PREP ───────────
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

            # ─────────── OVER TRACK MODE ───────────
            if voice_style == "over" and play_track and track.spotify_track_id:
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
                    continue

            # ─────────── BEFORE TRACK MODE ───────────
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

        # 🔁 TEMP: reset legacy flags
        flags.is_playing = False
        flags.stopped = True

        logger.debug("🧹 Playback state reset for %s/%s", decade, genre)
