from fastapi import APIRouter, Depends, Query
from sqlmodel import Session
from backend.database import get_db
from backend.services.xai_track_detail import regenerate_missing_track_details

router = APIRouter(prefix="/tts", tags=["TTS Regeneration"])

@router.post("/regenerate/missing-details")
def regenerate_missing_details(
    language: str = Query("English", description="Language for Casey Kasem-style detail"),
    db: Session = Depends(get_db)
):
    count = regenerate_missing_track_details(db, language=language)
    return {
        "message": f"✅ Regenerated 'detail' text for {count} track(s).",
        "count": count
    }
