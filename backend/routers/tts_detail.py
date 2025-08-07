from fastapi import APIRouter, Query, Depends
from pathlib import Path
import logging
from sqlmodel import Session, select
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.models import Track, TrackRanking, DecadeGenre
from backend.config import VOICE_ID_TRACK
from backend.utils.tts_diagnostics import get_missing_tts_info
from backend.services.tts.generate_tts_batch import generate_tts_batch

logger = logging.getLogger("tts_logger")

detail_router = APIRouter(
    prefix="/tts/detail",
    tags=["TTS - Track Detail"]
)


def generate_detail_filename(track):
    return f"{track['spotify_track_id']}.mp3"

@detail_router.post("/by-missing")
async def generate_missing_detail_tts(
    count: int = Query(-1, description="Number of missing detail TTS files to generate. Use -1 for all."),
    overwrite: bool = Query(False),
    play: bool = Query(False),
    db: Session = Depends(get_db)
):
    logger.info(f"🧠 Generating up to {count} missing detail TTS files")

    diagnostics = await get_missing_tts_info(
        db,
        check_intro_mp3=False,
        check_detail_mp3=True,
        check_artist_mp3=False
    )

    missing_tracks = diagnostics["missing_mp3"]["track_detail"]
    if count > 0:
        missing_tracks = missing_tracks[:count]

    missing_track_ids = {track.id for track in missing_tracks}

    results = db.exec(
        select(TrackRanking)
        .options(
            selectinload(TrackRanking.track),
            selectinload(TrackRanking.track).selectinload(Track.artist),
            selectinload(TrackRanking.decade_genre).selectinload(DecadeGenre.decade),
            selectinload(TrackRanking.decade_genre).selectinload(DecadeGenre.genre),
        )
    ).all()

    items = []
    missing_text_count = 0

    for ranking in results:
        track = ranking.track
        artist = track.artist

        if track.id in missing_track_ids:
            if not track.detail or not track.detail.strip():
                missing_text_count += 1
                continue

            items.append({
                "track_id": track.id,
                "spotify_track_id": track.spotify_track_id,
                "track_name": track.track_name,
                "artist_name": artist.artist_name,
                "album_name": track.album_name or "TopSpot40 Detail Tracks",
                "detail": track.detail,
            })

            if 0 < count <= len(items):
                break

    logger.info(f"🎯 Ready to generate {len(items)} detail TTS files")
    logger.info(f"🚫 Skipped {missing_text_count} tracks due to missing detail text")

    return generate_tts_batch(
        items=items,
        text_key="detail",
        voice_id=VOICE_ID_TRACK,
        output_dir=Path("data/mp3_files/track_detail_mp3_files"),
        filename_func=generate_detail_filename,
        log_prefix="Track Detail",
        overwrite=overwrite,
        play=play
    )
