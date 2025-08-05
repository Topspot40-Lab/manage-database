from fastapi import APIRouter, Query
from pathlib import Path
import logging
from fastapi import Depends
from sqlmodel import Session
from backend.database import get_db
from sqlmodel import select
from backend.models import Track
from sqlalchemy.orm import selectinload
from backend.models import TrackRanking, DecadeGenre  # make sure this is imported

from backend.services.track_cache import get_all_rank_entries
from backend.services.tts.elevenlabs_tts import generate_tts_mp3
from backend.config import VOICE_ID_INTRO
from backend.routers.tts_shared import add_metadata_to_mp3, log_tts_action
from backend.utils.tts_diagnostics import get_missing_tts_info
from backend.services.tts.generate_tts_batch import generate_tts_batch


logger = logging.getLogger("tts_logger")

# === Intro TTS ===
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

    logger.debug(f"🚨 Track type: {type(Track)} | Value: {Track}")

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
        logger.debug(f"🧪 Checking if missing: {filename_with_ext}")

        if filename_with_ext in missing_filenames:
            items.append({
                "track_id": track.id,
                "track_name": track.track_name,
                "artist_name": artist.artist_name,
                "album_name": track.album_name or "TopSpot40 Intro Tracks",
                "intro": ranking.intro,
                "rank": ranking.ranking,
                "decade": ranking.decade_genre.decade.decade_name,  # ✅ Correct
                "genre": ranking.decade_genre.genre.genre_name,  # ✅ Correct
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

@intro_router.post("/by-rank")
def generate_intro_tts_by_rank(
    start_rank: int = Query(..., ge=1),
    end_rank: int = Query(..., ge=1),
    overwrite: bool = Query(False),
    play: bool = Query(False)
):
    """
    Generate TTS for the 'intro' field of ranked tracks in the specified range.
    """
    logger.debug(f"🎙️ Mr Ed ... [Intro TTS] Requested ranks {start_rank} to {end_rank} | overwrite={overwrite} | play={play}")

    rankings = get_all_rank_entries()
    output_dir = Path("data/mp3_files/track_intro_mp3_files")
    output_dir.mkdir(parents=True, exist_ok=True)

    generated = []
    for track in rankings:
        rank = track.get("rank")
        intro = track.get("intro", "").strip()
        track_id = track.get("track_id")

        logger.debug(f"🔍 Rank {rank}: intro={bool(intro)} | track_id={track_id} | overwrite={overwrite}")

        if not rank or not (start_rank <= rank <= end_rank):
            logger.debug(f"⏭️ Skipping rank {rank}: outside requested range")
            continue

        if not intro:
            logger.warning(f"⚠️ No intro for rank {rank} — skipping TTS")
            continue

        if not track_id:
            logger.warning(f"⚠️ No track_id for rank {rank} — skipping TTS")
            continue

        decade = track.get("decade", "unknown")
        genre = track.get("genre", "unknown")
        out_path = output_dir / f"{decade}_{genre}_{rank:02}.mp3"

        if out_path.exists() and not overwrite:
            logger.debug(f"⏭️ MP3 exists and overwrite=False for {track_id}")
            log_tts_action("Track Intro", track_id, out_path, "⏭️ Skipped (exists)", play)
            continue

        logger.debug(f"🎧 Generating TTS for rank {rank}: {intro[:60]}...")
        generate_tts_mp3(intro, out_path, VOICE_ID_INTRO, overwrite=overwrite, play=play)

        track_name = track.get("track_name", "Unknown Track")
        artist_name = track.get("artist_name", "Unknown Artist")
        album_name = track.get("album_name") or "TopSpot40 Intro Tracks"
        add_metadata_to_mp3(out_path, track_name, artist_name, album_name)

        log_tts_action("Track Intro", track_id, out_path, "✅ Generated", play)
        generated.append(str(out_path))

    logger.info(f"✅ [Intro TTS] Generated {len(generated)} intro files")
    return {
        "message": f"✅ Generated {len(generated)} intro TTS files",
        "files": generated
    }
