# backend/routers/tts_artist.py

from fastapi import APIRouter, Query
from pathlib import Path
import logging

from backend.services.track_cache import get_all_rank_entries
from backend.services.tts.elevenlabs_tts import generate_tts_mp3
from backend.config import VOICE_ID_ARTIST
from backend.routers.tts_shared import add_metadata_to_mp3, log_tts_action

logger = logging.getLogger("tts_logger")

artist_router = APIRouter(
    prefix="/tts/artist",
    tags=["TTS - Artist"]
)


@artist_router.get("/list")
def list_unique_artists():
    """
    Returns a numbered list of unique artists with available descriptions.
    """
    logger.debug("🎨 Fetching all ranked tracks for unique artist listing...")
    rankings = get_all_rank_entries()

    seen = set()
    unique_artists = []

    for track in rankings:
        artist_id = track.get("spotify_artist_id")
        artist_name = track.get("artist_name", "Unknown Artist")
        artist_desc = track.get("artist_description", "").strip()

        if artist_id and artist_desc and artist_id not in seen:
            seen.add(artist_id)
            unique_artists.append({
                "index": len(unique_artists) + 1,
                "artist_id": artist_id,
                "artist_name": artist_name,
                "has_description": True
            })
            logger.debug(f"🎤 Added artist: {artist_name} (ID: {artist_id})")

    logger.info(f"🔍 Found {len(unique_artists)} unique artists with descriptions.")
    return {"total": len(unique_artists), "artists": unique_artists}


@artist_router.post("/by-range")
def generate_artist_tts_range(
    start: int = Query(..., ge=1, description="Start index (1-based) of artist list"),
    end: int = Query(..., ge=1, description="End index (inclusive) of artist list"),
    overwrite: bool = Query(False, description="Overwrite existing MP3 files"),
    play: bool = Query(False, description="Play audio after generation")
):
    """
    Generate artist TTS MP3 files for a specified range of artists (by index).
    """
    logger.debug(f"🎙️ TTS generation requested for artists {start} to {end} | overwrite={overwrite}, play={play}")

    if start > end:
        logger.warning("❌ Invalid range: start > end")
        return {"error": "Start index must be less than or equal to end index."}

    unique_artists = list_unique_artists()["artists"]
    selected = unique_artists[start - 1:end]
    logger.debug(f"📋 Selected {len(selected)} artist(s) from index {start} to {end}")

    rankings = get_all_rank_entries()
    artist_lookup = {
        t.get("spotify_artist_id"): t
        for t in rankings
        if t.get("spotify_artist_id") and t.get("artist_description")
    }

    output_dir = Path("data/mp3_files/artist_mp3_files")
    output_dir.mkdir(parents=True, exist_ok=True)

    generated = []

    for artist in selected:
        artist_id = artist["artist_id"]
        artist_name = artist["artist_name"]
        logger.debug(f"🎼 Processing artist: {artist_name} (ID: {artist_id})")

        track = artist_lookup.get(artist_id)

        if not track:
            logger.warning(f"⚠️ No matching track with description found for artist_id {artist_id}")
            continue

        artist_desc = track["artist_description"].strip()
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


@artist_router.post("/by-description-range")
def generate_artist_tts_descriptions(
    start: int = Query(..., ge=1),
    end: int = Query(..., ge=1),
    overwrite: bool = Query(False),
    play: bool = Query(False)
):
    """
    Generate TTS only for artist descriptions in the given index range.
    Currently behaves the same as /by-range. Can later be extended for selective description-only logic.
    """
    logger.debug(f"🎯 Generating artist descriptions from {start} to {end}")
    return generate_artist_tts_range(start=start, end=end, overwrite=overwrite, play=play)
