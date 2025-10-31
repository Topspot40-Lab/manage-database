# backend/routers/decade_genre_player.py
from fastapi import APIRouter, Query, Depends, BackgroundTasks
import asyncio
import logging
from typing import Literal
from sqlmodel import select, Session
from backend.database import get_db
from backend.models.dbmodels import Track, Artist, TrackRanking, DecadeGenre, Decade, Genre
from backend.services.radio_runtime import (
    log_header_and_texts,
    build_intro_jobs,
    narration_keys_for,
    play_narrations,
)

router = APIRouter(prefix="/supabase", tags=["Supabase: Play by Decade/Genre"])
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Core playback loop
# ─────────────────────────────────────────────
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
    """
    Perform full playback sequence for Decade/Genre mode:
    bed → intro → detail → artist → track.
    """
    from backend.routers.playback_control import _flags
    from backend.services.radio_runtime import _update_flags, _respect_user_controls
    from backend.services.play_policy import compute_play_seconds, sleep_with_skip
    from backend.services.spotify.playback import play_spotify_track
    from backend.state import skip_event

    logger.info(f"🎧 Background playback started: {decade}/{genre} ranks {start_rank}–{end_rank}")

    # ───────────────────────────────
    # 1️⃣ Query all matching tracks
    # ───────────────────────────────
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
        .order_by(TrackRanking.ranking)
    )

    rows = db.exec(q).all()
    if not rows:
        logger.warning(f"⚠️ No tracks found for {decade}/{genre}")
        return

    # ───────────────────────────────
    # 2️⃣ Sequential playback loop
    # ───────────────────────────────
    for track, artist, tr_rank, decade_obj, genre_obj in rows:
        try:
            rank = tr_rank.ranking
            logger.info("──────────────────────────────────────────────")
            logger.info(f"▶ Rank #{rank:02d}: {track.track_name} — {artist.artist_name}")

            # Update flags for this track
            _update_flags(
                phase="prelude",
                lang=tts_language,
                mode="decade_genre",
                rank=rank,
                track_name=track.track_name,
                artist_name=artist.artist_name,
            )
            await _respect_user_controls()


            # ───────────────────────────────
            # 3️⃣ Narration phase
            # ───────────────────────────────
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
                lang=tts_language, track=track, artist=artist
            )

            logger.debug(
                f"🎙️ Narration assets for rank #{rank}: "
                f"intro_jobs={len(intro_jobs)} | detail={bool(detail_key)} | artist={bool(artist_key)}"
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

            # ───────────────────────────────
            # 4️⃣ Track playback phase
            # ───────────────────────────────
            if play_track and track.spotify_track_id:
                _update_flags(
                    phase="track",
                    lang=tts_language,
                    mode="decade_genre",
                    rank=rank,
                    track_name=track.track_name,
                    artist_name=artist.artist_name,
                )
                await _respect_user_controls()

                logger.info(f"🎵 Now playing rank #{rank}: {track.track_name} — {artist.artist_name}")
                play_spotify_track(track.spotify_track_id)

                play_secs = compute_play_seconds(track)
                skipped = await sleep_with_skip(skip_event, play_secs)

                if skipped:
                    logger.info("⏭️ Skip triggered; moving to next track.")
                else:
                    logger.info("✅ Track finished normally.")
            else:
                logger.warning(f"⚠️ Missing Spotify track_id for rank {rank}.")

            await _respect_user_controls()
            await asyncio.sleep(0.5)  # short pacing delay between tracks

        except asyncio.CancelledError:
            logger.info("🛑 Playback loop cancelled mid-sequence.")
            break
        except Exception as e:
            logger.warning(f"⚠️ Error during playback loop (rank {rank}): {e}", exc_info=True)

    # ───────────────────────────────
    # 5️⃣ Wrap-up
    # ───────────────────────────────
    _flags.is_playing = False
    _flags.stopped = True
    logger.info(f"✅ Playback finished for {decade}/{genre} ranks {start_rank}–{end_rank}")


# ─────────────────────────────────────────────
# FastAPI route: /supabase/play-sequence
# ─────────────────────────────────────────────
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
    logger.info(f"▶ Received playback request for {decade}/{genre} | {start_rank}–{end_rank} (async mode)")

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

    return {
        "status": "started",
        "decade": decade,
        "genre": genre,
        "message": f"Playback started for {decade}/{genre} ranks {start_rank}–{end_rank}.",
    }


# ─────────────────────────────────────────────
# FastAPI route: /supabase/get-sequence
# ─────────────────────────────────────────────
@router.get("/get-sequence")
async def get_sequence_decade_genre(
    decade: str = Query(...),
    genre: str = Query(...),
    start_rank: int = Query(1),
    end_rank: int = Query(40),
    db: Session = Depends(get_db),
):
    """
    Retrieve track metadata for a given decade and genre.
    Used by the frontend to preview tracks before playback.
    """
    logger.info(f"📜 Fetching track preview for {decade}/{genre} ranks {start_rank}–{end_rank}")

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
        .order_by(TrackRanking.ranking)
    )

    rows = db.exec(q).all()
    if not rows:
        logger.warning(f"⚠️ No tracks found for {decade}/{genre}")
        return {"status": "empty", "decade": decade, "genre": genre, "tracks": []}

    tracks = []
    for track, artist, tr_rank, decade_obj, genre_obj in rows:
        tracks.append(
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
        )

    logger.info(f"✅ Returning {len(tracks)} tracks for {decade}/{genre}")
    return {
        "status": "ok",
        "decade": decade,
        "genre": genre,
        "total": len(tracks),
        "tracks": tracks,
    }
