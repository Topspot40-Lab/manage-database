from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select
from sqlalchemy import or_
import logging

from backend.database import get_db
from backend.models.dbmodels import Artist
from backend.services.xai_track_detail import regenerate_missing_track_details
from backend.services.xai_artist_detail import get_artist_descriptions_from_xai

router = APIRouter(prefix="/tts")
logger = logging.getLogger("STEP_9.MissingTTS")

@router.post("/regenerate/missing-details")
def regenerate_missing_details(
    language: str = Query("English", description="Language for detail and artist description"),
    regenerate_track_detail: bool = Query(False, description="Regenerate missing track 'detail' fields"),
    regenerate_artist_description: bool = Query(False, description="Regenerate missing artist descriptions"),
    db: Session = Depends(get_db)
):
    results = {}

    # 🔁 1. Regenerate missing Track details
    if regenerate_track_detail:
        track_count = regenerate_missing_track_details(db, language=language)
        results["track_details_regenerated"] = track_count
    else:
        results["track_details_regenerated"] = 0

    # 🎙️ 2. Regenerate missing Artist descriptions
    if regenerate_artist_description:
        # Step 1: Query artists with missing description
        stmt = select(Artist).where(
            or_(
                Artist.artist_description.is_(None),
                Artist.artist_description == ""
            )
        )
        artists = db.exec(stmt).all()

        if not artists:
            logger.info("✅ No artists missing descriptions.")
            results["artist_descriptions_regenerated"] = 0
        else:
            logger.info(f"🧠 Found {len(artists)} artists missing descriptions. Sending to XAI...")

            # Step 2: Prepare input for XAI
            input_list = [{"artist_name": artist.artist_name} for artist in artists]

            # Step 3: Call XAI
            responses = get_artist_descriptions_from_xai(input_list, language)

            # Step 4: Save responses to DB
            name_to_artist = {a.artist_name.lower(): a for a in artists}
            updated_count = 0

            for resp in responses:
                name = resp.get("artist_name", "").lower()
                desc = resp.get("artist_description", "").strip()
                if name and desc and name in name_to_artist:
                    artist = name_to_artist[name]
                    artist.artist_description = desc
                    updated_count += 1
                    logger.debug(f"📝 Updated description for: {artist.artist_name}")
                else:
                    logger.warning(f"⚠️ Skipping empty or unmatched response: {resp}")

            db.commit()
            results["artist_descriptions_regenerated"] = updated_count
            logger.info(f"✅ Regenerated {updated_count} artist descriptions.")
    else:
        results["artist_descriptions_regenerated"] = 0

    return {
        "message": "✅ Regeneration process completed.",
        **results
    }
