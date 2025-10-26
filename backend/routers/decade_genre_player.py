# backend/routers/decade_genre_player.py
from __future__ import annotations

import logging
from fastapi import APIRouter, Query, Depends
from sqlmodel import select, Session
from sqlalchemy import asc  # ✅ avoids type checker complaint
from typing import Literal

from backend.database import get_db
from backend.models.dbmodels import Track, Artist, TrackRanking, DecadeGenre, Decade, Genre
from backend.services.radio_runtime import (
    log_header_and_texts,
    build_intro_jobs,
    narration_keys_for,
    maybe_play_bed,
    play_narrations,
    play_track_with_skip,
)

router = APIRouter(prefix="/supabase", tags=["Supabase: Play by Decade/Genre"])
logger = logging.getLogger(__name__)


@router.get("/play-sequence")
async def play_sequence_decade_genre(
    decade: str = Query(..., description="Decade name, e.g. '1950s'"),
    genre: str = Query(..., description="Genre name, e.g. 'country'"),
    start_rank: int = Query(1),
    end_rank: int = Query(40),
    mode: Literal["count_up", "count_down", "random"] = Query("count_up"),
    tts_language: Literal["en", "es", "ptbr", "pt-BR"] = Query("en"),

    # playback flags (used below)
    play_intro: bool = Query(True),
    play_detail: bool = Query(True),
    play_artist_description: bool = Query(True),
    play_track: bool = Query(False),

    # text visibility flags (not used by backend playback, but accepted for API parity)
    text_intro: bool = Query(True),
    text_detail: bool = Query(False),
    text_artist_description: bool = Query(False),

    db: Session = Depends(get_db),
):
    """
    Stream a sequence for the given Decade + Genre.
    Plays intro/detail/artist narrations and (optionally) the track, honoring flags.
    """
    logger.info(
        "▶ Decade/Genre request: %s / %s | ranks %s..%s | mode=%s | lang=%s | flags: intro=%s detail=%s artist=%s track=%s",
        decade, genre, start_rank, end_rank, mode, tts_language, play_intro, play_detail, play_artist_description, play_track
    )

    # ─────────────────────────────────────────────
    # Build the base query with proper joins
    # ─────────────────────────────────────────────
    # noinspection PyArgumentList
    q = (
        select(Track, Artist, TrackRanking, Decade, Genre)
        .join(Artist, Artist.id == Track.artist_id)
        .join(TrackRanking, TrackRanking.track_id == Track.id)
        .join(DecadeGenre, DecadeGenre.id == TrackRanking.decade_genre_id)
        .join(Decade, Decade.id == DecadeGenre.decade_id)
        .join(Genre, Genre.id == DecadeGenre.genre_id)
        .where(
            Decade.decade_name == decade,
            Genre.genre_name == genre,
            TrackRanking.ranking >= start_rank,
            TrackRanking.ranking <= end_rank,
        )
        .order_by(asc(TrackRanking.ranking))
    )

    rows = db.exec(q).all()
    if not rows:
        return {
            "status": "error",
            "message": f"No tracks found for {decade}/{genre} in {start_rank}..{end_rank}",
            "sequence": [],
        }

    # Prepare the tuple list used by logging/intro-job helpers:
    # tr_rows expects items shaped like (TrackRanking, decade_name, genre_name)
    _tr_rows = [(tr_rank, decade.decade_name, genre.genre_name) for (_, _, tr_rank, decade, genre) in rows]

    # Optionally play a bed
    await maybe_play_bed()

    # Iterate and honor flags per item
    sequence_out = []
    for track, artist, tr_rank, decade, genre in rows:

        # Log header + compute localized/fallback texts
        intro_text, detail_text, artist_text = log_header_and_texts(
            lang=tts_language,
            track=track,
            artist=artist,
            tr_rows=[(tr_rank, decade.decade_name, genre.genre_name)]
        )

        intro_jobs = build_intro_jobs(
            lang=tts_language,
            tr_rows=[(tr_rank, decade.decade_name, genre.genre_name)]
        )

        detail_bucket, detail_key, artist_bucket, artist_key = narration_keys_for(
            lang=tts_language, track=track, artist=artist
        )

        # Play narrations according to flags
        await play_narrations(
            play_intro=play_intro,
            play_detail=play_detail,
            play_artist=play_artist_description,
            intro_jobs=intro_jobs,
            detail_bucket=detail_bucket,
            detail_key=detail_key,
            artist_bucket=artist_bucket,
            artist_key=artist_key,
        )

        # Optionally play the track itself
        if play_track and track.spotify_track_id:
            skipped = await play_track_with_skip(track=track, full_flag=True)
            logger.info("⏭️ skip=%s for rank %s", skipped, tr_rank.ranking)

        # ✅ Include the texts when the UI says it wants them
        sequence_out.append({
            "rank": tr_rank.ranking,
            "track_name": track.track_name,
            "artist_name": artist.artist_name,
            "year_released": getattr(track, "year_released", None),
            "duration_ms": getattr(track, "duration_ms", None),
            "album_artwork": getattr(track, "album_artwork", None),
            "spotify_track_id": getattr(track, "spotify_track_id", None),

            # only include if requested
            "intro": intro_text if text_intro else None,
            "detail_text": detail_text if text_detail else None,
            "artist_text": artist_text if text_artist_description else None,
        })

    return {
        "status": "success",
        "mode": "decade_genre",
        "decade": decade,
        "genre": genre,
        "language": tts_language,
        "count": len(sequence_out),
        "sequence": sequence_out,
        # Text flags are just echoed for the UI; backend already used the play_* ones
        "text_flags": {
            "intro": text_intro,
            "detail": text_detail,
            "artist": text_artist_description,
        },
    }
