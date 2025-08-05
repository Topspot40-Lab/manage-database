from fastapi import APIRouter, Query
from pathlib import Path
import logging
from fastapi import Depends
from sqlmodel import Session
from backend.database import get_db
from sqlmodel import select
from backend.models import Track, TrackRanking, DecadeGenre
from sqlalchemy.orm import selectinload

from backend.config import VOICE_ID_INTRO
from backend.utils.tts_diagnostics import get_missing_tts_info
from backend.services.tts.generate_tts_batch import generate_tts_batch

logger = logging.getLogger("tts_logger")

intro_router = APIRouter(
    prefix="/tts/intro",
    tags=["TTS - Intro"]
)


def generate_intro_filename(track):
    return f"{track['decade']}_{track['genre']}_{track['rank']:02}.mp3"


@intro_router.post("/by-missing")
async def generate_missing_intro_tts(
    count: int = Query(-1, description="Number of missing intro TTS files to generate. Use -1 for all."),
    overwrite: bool = Query(False),
    play: bool = Query(False),
    db: Session = Depends(get_db)
):
    logger.info(f"🧠 Generating up to {count} missing intro TTS files")

    diagnostics = await get_missing_tts_info(
        db,
        check_intro_mp3=True,
        check_detail_mp3=False,
        check_artist_mp3=False
    )

    missing_filenames = set(diagnostics["missing_mp3"]["track_intro"])
    if count > 0:
        missing_filenames = set(list(missing_filenames)[:count])

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
    for ranking in results:
        track = ranking.track
        artist = track.artist
        decade = ranking.decade_genre.decade.decade_name
        genre = ranking.decade_genre.genre.genre_name

        filename = generate_intro_filename({
            "decade": decade,
            "genre": genre,
            "rank": ranking.ranking
        })

        filename_with_ext = filename if filename.endswith(".mp3") else f"{filename}.mp3"

        if filename_with_ext in missing_filenames:
            items.append({
                "track_id": track.id,
                "track_name": track.track_name,
                "artist_name": artist.artist_name,
                "album_name": track.album_name or "TopSpot40 Intro Tracks",
                "intro": ranking.intro,
                "rank": ranking.ranking,
                "decade": decade,
                "genre": genre,
            })

            if 0 < count <= len(items):
                break

    logger.debug(f"🧪 Found {len(items)} missing intro TTS items to generate")

    return generate_tts_batch(
        items=items,
        text_key="intro",
        voice_id=VOICE_ID_INTRO,
        output_dir=Path("data/mp3_files/track_intro_mp3_files"),
        filename_func=generate_intro_filename,
        log_prefix="Track Intro",
        overwrite=overwrite,
        play=play
    )
