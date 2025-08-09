from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select
from backend.database import get_db
from backend.models import Track, Artist, Specialty, SpecialtyRanking
from backend.utils.json_helpers import load_full_json_file
import logging

router = APIRouter(tags=["Insert: Specialty"])
logger = logging.getLogger("insert_specialty")

LANGUAGE_CODE_MAP = {
    "english": "en",
    "spanish": "es",
    "french": "fr",
    "german": "de",
    "italian": "it",
    "portuguese": "pt",
    "japanese": "ja",
    "chinese": "zh",
    "korean": "ko"
}

@router.post("/specialty")
def insert_json_to_specialty_db(
        filename: str = Query(..., description="Path to the JSON file to insert"),
        db: Session = Depends(get_db)
):
    logger.info(f"📁 Inserting JSON into Specialty DB from file: {filename}")

    # Load the JSON data
    data = load_full_json_file(filename)

    specialty_name = data["genre"]
    description = f"{data['genre']} - {data['decade']}"

    # 🔁 Normalize and convert language to 2-letter code
    language_full = data.get("language", "english").strip().lower()
    language = LANGUAGE_CODE_MAP.get(language_full, "en")

    tracks = data["tracks"]

    # 1. Check or create specialty
    stmt = select(Specialty).where(Specialty.specialty_name == specialty_name, Specialty.language == language)
    specialty = db.exec(stmt).first()
    if not specialty:
        specialty = Specialty(
            specialty_name=specialty_name,
            description=description,
            language=language
        )
        db.add(specialty)
        db.commit()
        db.refresh(specialty)
        logger.info(f"✅ Created new specialty: {specialty_name} ({language})")

    inserted = 0
    for track in tracks:
        track_id = track.get("track_id")
        if not track_id:
            logger.warning("⚠️ Skipping track with no track_id")
            continue

        artist_name = track["artist_name"]

        # 2. Ensure artist exists
        artist_stmt = select(Artist).where(Artist.artist_name == artist_name)
        artist = db.exec(artist_stmt).first()
        if not artist:
            artist = Artist(
                artist_name=artist_name,
                artist_description=track.get("artist_description", ""),
                language=language
            )
            db.add(artist)
            db.commit()
            db.refresh(artist)
            logger.info(f"➕ Added artist: {artist_name} ({language})")

        # 3. Ensure track exists
        track_stmt = select(Track).where(Track.spotify_track_id == track_id)
        existing_track = db.exec(track_stmt).first()
        if not existing_track:
            new_track = Track(
                track_name=track["track_name"],
                spotify_track_id=track_id,
                artist_id=artist.id,
                album_name=track.get("album_name", ""),
                duration_ms=track.get("duration_ms"),
                detail=track.get("detail", ""),
                language=language
            )
            db.add(new_track)
            db.commit()
            db.refresh(new_track)
            logger.info(f"🎵 Added track: {track['track_name']} ({language})")

        # 4. Add specialty ranking
        specialty_rank = SpecialtyRanking(
            specialty_id=specialty.id,
            track_id=track_id,
            ranking=track["rank"],
            intro=track.get("intro", ""),
            detail=track.get("detail", ""),
            artist_id=artist.id,
            language=language
        )
        db.add(specialty_rank)
        inserted += 1

    db.commit()
    logger.info(f"✅ Inserted {inserted} track rankings into specialty_ranking")

    return {
        "message": "✅ Specialty JSON inserted successfully.",
        "specialty": specialty_name,
        "language": language,
        "tracks_inserted": inserted
    }
