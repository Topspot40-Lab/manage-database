# backend/routers/decade_genre_player.py
from __future__ import annotations

import asyncio
import logging
import random
from typing import Literal

from fastapi import APIRouter, Query, Depends
from sqlmodel import select

from backend.database import get_db_session, get_db
from backend.models.dbmodels import (
    Track,
    Artist,
    TrackRanking,
    DecadeGenre,
    Decade,
    Genre,
)

from backend.services.spotify.playback import play_spotify_track
from backend.routers.playback_control import (
    start_new_sequence,
    _flags,
)

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

from backend.config.volume import PLAY_FULL_TRACK

router = APIRouter(prefix="/supabase/decade-genre", tags=["Supabase: Decade/Genre"])
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# INTERNAL: LOAD TRACKS FOR A DECADE/GENRE RANGE
# ─────────────────────────────────────────────
def _load_decade_genre_rows(
    *,
    decade: str,
    genre: str,
    start_rank: int,
    end_rank: int,
):
    """
    Query all tracks for (decade, genre) in [start_rank, end_rank].
    Returns a list of tuples:
      (Track, Artist, TrackRanking, Decade, Genre)
    """
    with get_db_session() as db:
        q = (
            select(Track, Artist, TrackRanking, Decade, Genre)
            .join(Artist, Artist.id == Track.artist_id)
            .join(TrackRanking, TrackRanking.track_id == Track.id)
            .join(DecadeGenre, DecadeGenre.id == TrackRanking.decade_genre_id)
            .join(Decade, Decade.id == DecadeGenre.decade_id)
            .join(Genre, Genre.id == DecadeGenre.genre_id)
            .where(
                Decade.slug == decade,
                Genre.slug == genre,
                TrackRanking.ranking >= start_rank,
                TrackRanking.ranking <= end_rank,
            )
        )
        return db.exec(q).all()


def _order_rows_for_mode(rows, mode: Literal["count_up", "count_down", "random"]):
    """
    Sort or shuffle rows according to playback mode.
    """
    if not rows:
        return rows

    if mode == "count_up":
        rows.sort(key=lambda r: r[2].ranking)
    elif mode == "count_down":
        rows.sort(key=lambda r: r[2].ranking, reverse=True)
    else:
        random.shuffle(rows)

    return rows


# ─────────────────────────────────────────────
# INTERNAL BACKGROUND TASK (RUNS FULL SEQUENCE)
# ─────────────────────────────────────────────
async def _run_play_sequence_decade_genre(
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

    # Reset high-level flags for this sequence
    _flags.cancel_requested = False
    _flags.is_playing = True
    _flags.mode = "decade_genre"
    _flags.context = {"decade": decade, "genre": genre}

    try:
        # ─────────────────────────────────────────
        # DB QUERY: Fetch all tracks in range
        # ─────────────────────────────────────────
        rows = _load_decade_genre_rows(
            decade=decade,
            genre=genre,
            start_rank=start_rank,
            end_rank=end_rank,
        )

        if not rows:
            logger.warning("⚠️ No tracks found for %s/%s", decade, genre)
            return

        # Order rows for the selected playback mode
        rows = _order_rows_for_mode(rows, mode)

        # ─────────────────────────────────────────
        # MAIN LOOP
        # ─────────────────────────────────────────
        for track, artist, tr_rank, decade_obj, genre_obj in rows:
            # Global cancel check BEFORE doing anything expensive
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

            # UI → update state for "prelude"
            _update_flags(
                phase="prelude",
                lang=tts_language,
                mode="decade_genre",
                rank=rank,
                track_name=track.track_name,
                artist_name=artist.artist_name,
            )
            await _respect_user_controls()

            # ─────────── Narration setup (logging + MP3 keys) ───────────
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

            # ─────────────────────────────────────────
            # VOICE STYLE: OVER vs BEFORE TRACK
            # ─────────────────────────────────────────
            if voice_style == "over" and play_track and track.spotify_track_id:
                # DJ-style: main track first, narrations ON TOP
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

                # Wait out track with skip support
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
                    logger.info("⏭️ Track skipped — continuing to next.")
                    continue

            else:
                # Classic radio style: voice BEFORE track, with bed under intro
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
                        logger.info("⏭️ Track skipped — continuing to next.")
                        continue

            # Respect pause/stop again at the end of each track
            await _respect_user_controls()
            await asyncio.sleep(0.5)

        logger.info("🎉 Sequence finished (decade/genre %s/%s).", decade, genre)

    except asyncio.CancelledError:
        logger.info("⛔ Sequence task cancelled (new sequence or stop).")
        raise
    except Exception as e:
        logger.warning("⚠️ Sequence error for %s/%s: %s", decade, genre, e)
    finally:
        _flags.is_playing = False
        _flags.cancel_requested = False
        _flags.context = {"decade": decade, "genre": genre}
        logger.debug("🧹 Sequence flags reset for %s/%s", decade, genre)


# ─────────────────────────────────────────────
# SINGLE-PLAY HELPER (WRAPS SEQUENCE RUNNER)
# ─────────────────────────────────────────────
async def play_one_server_side(
    *,
    decade: str,
    genre: str,
    rank: int,
    tts_language: str = "en",
    mode: Literal["count_up", "count_down", "random"] = "count_up",
    play_intro: bool = True,
    play_detail: bool = True,
    play_artist_description: bool = True,
    play_track: bool = True,
    text_intro: bool = False,
    text_detail: bool = False,
    text_artist_description: bool = False,
    voice_style: Literal["before", "over"] = "before",
) -> None:
    """
    Play a *single* track for a given decade/genre/rank, using the
    same pipeline as the full sequence runner, including voice_style.

    Equivalent to: play-sequence(start_rank=rank, end_rank=rank)
    but callable directly from other routers / CLI tools.
    """
    logger.info(
        "🎯 Single-play request — %s/%s rank #%d, mode=%s, lang=%s, voice_style=%s",
        decade,
        genre,
        rank,
        mode,
        tts_language,
        voice_style,
    )

    await _run_play_sequence_decade_genre(
        decade=decade,
        genre=genre,
        start_rank=rank,
        end_rank=rank,
        mode=mode,
        tts_language=tts_language,
        play_intro=play_intro,
        play_detail=play_detail,
        play_artist_description=play_artist_description,
        play_track=play_track,
        text_intro=text_intro,
        text_detail=text_detail,
        text_artist_description=text_artist_description,
        voice_style=voice_style,
    )


# ─────────────────────────────────────────────
# FAST PLAY-FIRST (INSTANT START)
# ─────────────────────────────────────────────
@router.get("/play-first")
async def play_first_decade_genre(
    decade: str = Query(...),
    genre: str = Query(...),
    mode: Literal["count_up", "count_down", "random"] = Query("count_up"),
    tts_language: Literal["en", "es", "ptbr", "pt-BR"] = Query("en"),
    play_intro: bool = Query(True),
    play_detail: bool = Query(True),
    play_artist_description: bool = Query(True),
    play_track: bool = Query(True),
    text_intro: bool = Query(True),
    text_detail: bool = Query(False),
    text_artist_description: bool = Query(False),
    voice_style: Literal["before", "over"] = Query("before"),
):
    logger.info(
        "⚡ FAST PLAY-FIRST (SERIALIZED): %s/%s lang=%s voice_style=%s",
        decade,
        genre,
        tts_language,
        voice_style,
    )

    async def _run_serial_fast_then_full():
        # ✅ First: rank #1 only
        await _run_play_sequence_decade_genre(
            decade=decade,
            genre=genre,
            start_rank=1,
            end_rank=1,
            mode=mode,
            tts_language=tts_language,
            play_intro=play_intro,
            play_detail=play_detail,
            play_artist_description=play_artist_description,
            play_track=play_track,
            text_intro=text_intro,
            text_detail=text_detail,
            text_artist_description=text_artist_description,
            voice_style=voice_style,
        )

        # ✅ THEN continue with 2–40 (no overlap possible)
        await _run_play_sequence_decade_genre(
            decade=decade,
            genre=genre,
            start_rank=2,
            end_rank=40,
            mode=mode,
            tts_language=tts_language,
            play_intro=play_intro,
            play_detail=play_detail,
            play_artist_description=play_artist_description,
            play_track=play_track,
            text_intro=text_intro,
            text_detail=text_detail,
            text_artist_description=text_artist_description,
            voice_style=voice_style,
        )

    # ✅ Only ONE task exists now
    await start_new_sequence(_run_serial_fast_then_full())

    return {
        "status": "started-fast-serialized",
        "decade": decade,
        "genre": genre,
        "mode": mode,
        "voice_style": voice_style,
    }



# ─────────────────────────────────────────────
# START NEW SEQUENCE (ROUTER)
# ─────────────────────────────────────────────
@router.get("/play-sequence")
async def play_sequence_decade_genre(
    decade: str = Query(...),
    genre: str = Query(...),
    start_rank: int = Query(1),
    end_rank: int = Query(40),
    mode: Literal["count_up", "count_down", "random"] = Query("count_up"),
    tts_language: Literal["en", "es", "ptbr", "pt-BR"] = Query("en"),
    play_intro: bool = Query(True),
    play_detail: bool = Query(True),
    play_artist_description: bool = Query(True),
    play_track: bool = Query(False),
    text_intro: bool = Query(True),
    text_detail: bool = Query(False),
    text_artist_description: bool = Query(False),
    voice_style: Literal["before", "over"] = Query("before"),
):
    logger.info(
        "▶ Launch request: %s/%s %d-%d mode=%s lang=%s voice_style=%s",
        decade,
        genre,
        start_rank,
        end_rank,
        mode,
        tts_language,
        voice_style,
    )

    coro = _run_play_sequence_decade_genre(
        decade=decade,
        genre=genre,
        start_rank=start_rank,
        end_rank=end_rank,
        mode=mode,
        tts_language=tts_language,
        play_intro=play_intro,
        play_detail=play_detail,
        play_artist_description=play_artist_description,
        play_track=play_track,
        text_intro=text_intro,
        text_detail=text_detail,
        text_artist_description=text_artist_description,
        voice_style=voice_style,
    )

    await start_new_sequence(coro)

    return {
        "status": "started",
        "decade": decade,
        "genre": genre,
        "mode": mode,
        "range": [start_rank, end_rank],
        "voice_style": voice_style,
    }


# ─────────────────────────────────────────────
# FRONTEND METADATA (SEQUENCE PREVIEW)
# ─────────────────────────────────────────────
@router.get("/get-sequence")
async def get_sequence_decade_genre(
    decade: str = Query(...),
    genre: str = Query(...),
    start_rank: int = Query(1),
    end_rank: int = Query(40),
    db=Depends(get_db),
):
    q = (
        select(Track, Artist, TrackRanking, Decade, Genre)
        .join(Artist, Artist.id == Track.artist_id)
        .join(TrackRanking, TrackRanking.track_id == Track.id)
        .join(DecadeGenre, DecadeGenre.id == TrackRanking.decade_genre_id)
        .join(Decade, Decade.id == DecadeGenre.decade_id)
        .join(Genre, Genre.id == DecadeGenre.genre_id)
        .where(
            Decade.slug == decade,
            Genre.slug == genre,
            TrackRanking.ranking >= start_rank,
            TrackRanking.ranking <= end_rank,
        )
        .order_by(TrackRanking.ranking)
    )

    rows = db.exec(q).all()

    if not rows:
        return {"status": "empty", "tracks": []}

    tracks = [
        {
            "rank": tr_rank.ranking,
            "trackName": track.track_name,
            "artistName": artist.artist_name,
            "yearReleased": getattr(track, "year_released", None),
            "durationMs": getattr(track, "duration_ms", None),
            "albumArtwork": getattr(track, "album_artwork", None),
            "spotifyTrackId": getattr(track, "spotify_track_id", None),
            "albumName": getattr(track, "album_name", None),
        }
        for track, artist, tr_rank, _, _ in rows
    ]

    return {"status": "ok", "total": len(tracks), "tracks": tracks}


