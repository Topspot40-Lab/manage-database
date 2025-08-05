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

logger = logging.getLogger("tts_logger")

artist_router = APIRouter(
    prefix="/tts/artist",
    tags=["TTS - Artist"]
)

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

    artist_dir = Path("data/mp3_files/artist_mp3_files")
    artist_dir.mkdir(parents=True, exist_ok=True)

    artists = []
    for index, artist in enumerate(results, start=1):
        mp3_path = artist_dir / f"{artist.spotify_artist_id}.mp3"

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

    output_dir = Path("data/mp3_files/artist_mp3_files")
    output_dir.mkdir(parents=True, exist_ok=True)

    generated = []

    for artist in selected:
        artist_id = artist["artist_id"]
        artist_name = artist["artist_name"]
        logger.debug(f"🎼 Processing artist: {artist_name} (ID: {artist_id})")

        artist_desc = artist.get("artist_description", "").strip()
        if not artist_desc:
            logger.warning(f"⚠️ No description found for artist: {artist_name} (ID: {artist_id})")
            continue

        out_path = output_dir / f"{artist_id}.mp3"

        if out_path.exists() and not overwrite:
            logger.info(f"⏭️ Skipping existing file for {artist_name} (ID: {artist_id})")
            log_tts_action("Artist", artist_id, out_path, "⏭️ Skipped (exists)", play)
            continue

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
