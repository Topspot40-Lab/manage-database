# backend/routers/tts_artist.py

from fastapi import APIRouter, Query, Depends
from sqlmodel import Session, select
from sqlalchemy import and_
from pathlib import Path
import logging

from backend.database import get_db
from backend.models import Artist
from backend.services.tts.elevenlabs_tts import generate_tts_mp3
from backend.config import VOICE_ID_ARTIST
from backend.routers.tts_shared import add_metadata_to_mp3, log_tts_action
from backend.utils.tts_diagnostics import get_missing_tts_info
from backend.services.tts.generate_tts_batch import generate_tts_batch

logger = logging.getLogger("tts_logger")

artist_router = APIRouter(
    prefix="/tts/artist",
    tags=["TTS - Artist"]
)

# Central output directory for all artist MP3s
ARTIST_MP3_DIR = Path("data/mp3_files/artist_mp3_files")
ARTIST_MP3_DIR.mkdir(parents=True, exist_ok=True)


# === GET /tts/artist/list ===
@artist_router.get("/list")
def list_unique_artists(db: Session = Depends(get_db)):
    """
    Returns a numbered list of unique artists from the Artist table
    who have a non-empty description.
    """
    logger.debug("🎨 Fetching all artists with descriptions from database...")

    results = db.exec(
        select(Artist).where(
            and_(
                Artist.__table__.c.artist_description.is_not(None),
                Artist.__table__.c.artist_description != ""
            )
        )
    ).all()

    artists = []
    for index, artist in enumerate(results, start=1):
        mp3_path = ARTIST_MP3_DIR / f"{artist.spotify_artist_id}.mp3"

        artist_info = {
            "index": index,
            "artist_id": artist.spotify_artist_id,
            "artist_name": artist.artist_name,
            "artist_description": artist.artist_description,
            "has_description": True,
            "has_mp3": mp3_path.exists()
        }

        artists.append(artist_info)

        logger.debug(
            f"{index:02d}. 🎤 {artist.artist_name} "
            f"(ID: {artist.spotify_artist_id}) | "
            f"MP3: {'✅' if artist_info['has_mp3'] else '❌'}"
        )

    logger.info(f"🔍 Found {len(artists)} artists with descriptions.")
    return {"total": len(artists), "artists": artists}


# === POST /tts/artist/by-range ===
@artist_router.post("/by-range")
def generate_artist_tts_range(
    start: int = Query(..., ge=1, description="Start index (1-based) of artist list"),
    end: int = Query(..., ge=1, description="End index (inclusive) of artist list"),
    overwrite: bool = Query(False, description="Overwrite existing MP3 files"),
    play: bool = Query(False, description="Play audio after generation"),
    db: Session = Depends(get_db)
):
    """
    Generate artist TTS MP3 files for a specified range of artists (by index).
    """
    logger.debug(f"🎙️ TTS generation requested for artists {start} to {end} | overwrite={overwrite}, play={play}")

    if start > end:
        logger.warning("❌ Invalid range: start > end")
        return {"error": "Start index must be less than or equal to end index."}

    unique_artists = list_unique_artists(db)["artists"]
    selected = unique_artists[start - 1:end]

    logger.debug(f"📋 Selected {len(selected)} artist(s) from index {start} to {end}")

    # ✅ Filter out artists that already have MP3s, unless overwrite=True
    if not overwrite:
        selected = [
            artist for artist in selected
            if not (ARTIST_MP3_DIR / f"{artist['artist_id']}.mp3").exists()
        ]

    logger.debug(f"📋 Artists needing TTS generation: {len(selected)}")

    generated = []

    for artist in selected:
        artist_id = artist["artist_id"]
        artist_name = artist["artist_name"]
        logger.debug(f"🎼 Processing artist: {artist_name} (ID: {artist_id})")

        artist_desc = (artist.get("artist_description") or "").strip()
        if not artist_desc:
            logger.warning(f"⚠️ No description found for artist: {artist_name} (ID: {artist_id})")
            continue

        out_path = ARTIST_MP3_DIR / f"{artist_id}.mp3"

        logger.debug(f"🔊 Generating TTS for {artist_name} → {out_path}")
        generate_tts_mp3(artist_desc, out_path, VOICE_ID_ARTIST, overwrite=overwrite, play=play)

        track_name = f"Artist Bio: {artist_name}"
        album_name = "TopSpot40 Artist Bios"
        add_metadata_to_mp3(out_path, track_name, artist_name, album_name)

        log_tts_action("Artist", artist_id, out_path, "✅ Generated", play)
        generated.append(str(out_path))

    logger.info(f"✅ Generated {len(generated)} artist TTS file(s) in range {start}-{end}")
    return {
        "message": f"✅ Generated {len(generated)} artist TTS files in range {start}-{end}",
        "files": generated
    }

@artist_router.post("/by-missing")
async def generate_missing_artist_tts(
    count: int = Query(-1, description="Number of missing artist TTS files to generate. Use -1 for all."),
    overwrite: bool = Query(False),
    play: bool = Query(False),
    db: Session = Depends(get_db)
):
    logger.info(f"🧠 Generating up to {count} missing artist TTS files")

    diagnostics = await get_missing_tts_info(
        db,
        check_intro_mp3=False,
        check_detail_mp3=False,
        check_artist_mp3=True
    )

    missing_artists = diagnostics["missing_mp3"].get("artist_mp3", [])

    if count > 0:
        missing_artists = missing_artists[:count]

    def generate_artist_filename(item):
        return f"{item['spotify_artist_id']}.mp3"

    items = []
    for artist in missing_artists:
        desc = (artist.artist_description or "").strip()
        if not desc:
            continue

        items.append({
            "spotify_artist_id": artist.spotify_artist_id,
            "artist_name": artist.artist_name,
            "artist_description": desc,
        })

        if 0 < count <= len(items):
            break

    logger.info(f"🎯 Ready to generate {len(items)} artist TTS files")

    return generate_tts_batch(
        items=items,
        text_key="artist_description",
        voice_id=VOICE_ID_ARTIST,
        output_dir=ARTIST_MP3_DIR,
        filename_func=generate_artist_filename,
        log_prefix="Artist",
        overwrite=overwrite,
        play=play
    )
