from fastapi import APIRouter, Query, Depends, BackgroundTasks
import logging
from sqlmodel import select, Session
from sqlalchemy import asc
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


async def _run_play_sequence_decade_genre(
    *,
    decade: str,
    genre: str,
    start_rank: int,
    end_rank: int,
    mode: str,
    tts_language: str,
    play_intro: bool,
    play_detail: bool,
    play_artist_description: bool,
    play_track: bool,
    text_intro: bool,
    text_detail: bool,
    text_artist_description: bool,
    db: Session,
):
    """Internal worker that performs actual playback."""
    logger.info("🎧 Background playback started: %s / %s ranks %s–%s", decade, genre, start_rank, end_rank)

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
        logger.warning("⚠️ No tracks found for %s/%s", decade, genre)
        return

    await maybe_play_bed()

    for track, artist, tr_rank, decade_obj, genre_obj in rows:
        intro_text, detail_text, artist_text = log_header_and_texts(
            lang=tts_language,
            track=track,
            artist=artist,
            tr_rows=[(tr_rank, decade_obj.decade_name, genre_obj.genre_name)]
        )

        intro_jobs = build_intro_jobs(
            lang=tts_language,
            tr_rows=[(tr_rank, decade_obj.decade_name, genre_obj.genre_name)]
        )

        detail_bucket, detail_key, artist_bucket, artist_key = narration_keys_for(
            lang=tts_language, track=track, artist=artist
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
        )

        if play_track and track.spotify_track_id:
            skipped = await play_track_with_skip(track=track, full_flag=True)
            logger.info("⏭️ skip=%s for rank %s", skipped, tr_rank.ranking)

    logger.info("✅ Playback finished for %s / %s", decade, genre)


@router.get("/play-sequence")
async def play_sequence_decade_genre(
    background_tasks: BackgroundTasks,
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
    db: Session = Depends(get_db),
):
    """Starts playback asynchronously and returns immediately."""
    logger.info(
        "▶ Received playback request for %s / %s | %s–%s (async mode)",
        decade, genre, start_rank, end_rank
    )

    # Launch playback in background
    background_tasks.add_task(
        _run_play_sequence_decade_genre,
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
        db=db,
    )

    # Immediate non-blocking response
    return {"status": "started", "decade": decade, "genre": genre}
