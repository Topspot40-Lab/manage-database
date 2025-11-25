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

# playback control manager
from backend.routers.playback_control import (
    start_new_sequence,
    cancel_current_sequence,
    _flags,
)

# narration + runtime playback
from backend.services.radio_runtime import (
    log_header_and_texts,
    build_intro_jobs,
    narration_keys_for,
    play_narrations,
    _update_flags,
    _respect_user_controls,
    play_track_with_skip,     # Unified track player
)


router = APIRouter(prefix="/supabase", tags=["Supabase: Play by Decade/Genre"])
logger = logging.getLogger(__name__)


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
):
    logger.info(f"🎧 Starting sequence: {decade}/{genre} {start_rank}-{end_rank} mode={mode}")

    # 1️⃣ Load tracks inside background task
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

    # Sorting & randomization
    if mode == "count_up":
        rows.sort(key=lambda r: r[2].ranking)
    elif mode == "count_down":
        rows.sort(key=lambda r: r[2].ranking, reverse=True)
    else:
        random.shuffle(rows)

    # Update global playback state
    _flags.mode = "decade_genre"
    _flags.context = {"decade": decade, "genre": genre}

    # 2️⃣ Main playback loop
    for track, artist, tr_rank, decade_obj, genre_obj in rows:
        rank = tr_rank.ranking

        if _flags.cancel_requested:
            logger.info("🛑 Cancel requested — stopping sequence.")
            break

        logger.info("──────────────────────────────────────")
        logger.info(f"▶ Rank #{rank:02d}: {track.track_name} — {artist.artist_name}")

        # UI update
        _update_flags(
            phase="prelude",
            lang=tts_language,
            mode="decade_genre",
            rank=rank,
            track_name=track.track_name,
            artist_name=artist.artist_name,
        )
        await _respect_user_controls()

        # ─────────── Narration Phase ───────────
        intro_text, detail_text, artist_text = log_header_and_texts(
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
        )

        # ─────────── Track Playback ───────────
        if play_track:
            await play_track_with_skip(
                track,
                lang=tts_language,
                mode="decade_genre",
                rank=rank,
                track_name=track.track_name,
                artist_name=artist.artist_name,
            )

        await _respect_user_controls()
        await asyncio.sleep(0.5)

    # Cleanup
    await cancel_current_sequence()
    logger.info("✅ Sequence finished cleanly.")


# ─────────────────────────────────────────────
# PUBLIC: START NEW PLAY SEQUENCE
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
):
    logger.info(
        f"▶ Launch request: {decade}/{genre} {start_rank}-{end_rank} mode={mode}, lang={tts_language}"
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
    )

    await start_new_sequence(coro)

    return {
        "status": "started",
        "decade": decade,
        "genre": genre,
        "mode": mode,
        "range": [start_rank, end_rank],
    }


# ─────────────────────────────────────────────
# PUBLIC: GET METADATA FOR FRONTEND
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
