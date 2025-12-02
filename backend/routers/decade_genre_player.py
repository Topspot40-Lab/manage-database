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
    cancel_current_sequence,
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
    _ensure_volume_ok,  # 👈 add this
)


from backend.config.volume import PLAY_FULL_TRACK


router = APIRouter(prefix="/supabase", tags=["Supabase: Play by Decade/Genre"])
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# INTERNAL BACKGROUND TASK (RUNS FULL SEQUENCE)
# ─────────────────────────────────────────────


# ... keep all your existing imports above ...

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
):
    logger.info(
        f"🎧 Starting sequence: {decade}/{genre} {start_rank}-{end_rank} "
        f"mode={mode}, voice_style={voice_style}"
    )

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
        rows = db.exec(q).all()

    if not rows:
        logger.warning(f"⚠️ No tracks found for {decade}/{genre}")
        await cancel_current_sequence()
        return

    # ordering
    if mode == "count_up":
        rows.sort(key=lambda r: r[2].ranking)
    elif mode == "count_down":
        rows.sort(key=lambda r: r[2].ranking, reverse=True)
    else:
        random.shuffle(rows)

    _flags.mode = "decade_genre"
    _flags.context = {"decade": decade, "genre": genre}

    # ─────────────────────────────────────────────
    # MAIN LOOP
    # ─────────────────────────────────────────────
    for track, artist, tr_rank, decade_obj, genre_obj in rows:
        _flags.cancel_requested = False

        rank = tr_rank.ranking

        # ─────────────────────────────────────────────
        # HANDLE NEXT TRACK (User skip / next)
        # ─────────────────────────────────────────────
        if _flags.cancel_requested:
            logger.info("⏭️ Next-track skip detected — launching next track.")

            # Compute next rank intelligently based on mode
            if mode == "count_up":
                next_rank = rank + 1
            elif mode == "count_down":
                next_rank = rank - 1
            else:  # random mode
                next_rank = rank  # rerun with new shuffle

            # Prevent going out of bounds
            if next_rank < start_rank or next_rank > end_rank:
                logger.info("⏹ Sequence ended — next rank out of range.")
                break

            # Build a new mini-sequence for only the next track
            coro = _run_play_sequence_decade_genre(
                decade=decade,
                genre=genre,
                start_rank=next_rank,
                end_rank=next_rank,
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

            # Launch the next sequence immediately
            await start_new_sequence(coro)
            return


        logger.info(f"▶ Rank #{rank:02d}: {track.track_name} — {artist.artist_name}")

        # UI → update state
        _update_flags(
            phase="prelude",
            lang=tts_language,
            mode="decade_genre",
            rank=rank,
            track_name=track.track_name,
            artist_name=artist.artist_name,
        )
        await _respect_user_controls()

        # ─────────── Narration setup ───────────
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

        # ─────────────────────────────────────────────
        # 1️⃣ VOICE BEFORE vs OVER TRACK
        # ─────────────────────────────────────────────
        if voice_style == "over" and play_track and track.spotify_track_id:
            # Start main track first (DJ over-the-song style)
            logger.info("🎧 OVER-TRACK: starting main track before narration.")

            # ✅ Make sure device volume isn't stuck at 0 after a skip/cancel
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

            # Now just wait out the remaining track time with skip support
            await play_track_with_skip(
                track=track,
                lang=tts_language,
                mode="decade_genre",
                rank=rank,
                track_name=track.track_name,
                artist_name=artist.artist_name,
                full_flag=PLAY_FULL_TRACK,
                already_playing=True,   # important!
            )

        else:
            # Classic mode: voice BEFORE the song, with bed under intro
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

            # Then track
            if play_track:
                await play_track_with_skip(
                    track=track,
                    lang=tts_language,
                    mode="decade_genre",
                    rank=rank,
                    track_name=track.track_name,
                    artist_name=artist.artist_name,
                    full_flag=PLAY_FULL_TRACK,
                )

        await _respect_user_controls()
        await asyncio.sleep(0.5)

    _flags.is_playing = False
    _flags.cancel_requested = False
    logger.info("🎉 Sequence completed normally (no cancel).")


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

    This is basically: play-sequence(start_rank=rank, end_rank=rank)
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
# START NEW SEQUENCE
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
        f"▶ Launch request: {decade}/{genre} {start_rank}-{end_rank} "
        f"mode={mode}, lang={tts_language}, voice_style={voice_style}"
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
# FRONTEND METADATA
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
