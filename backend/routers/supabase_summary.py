from fastapi import APIRouter, Query, Depends
from sqlmodel import Session, select
import logging

from backend.database import get_db
from backend.models import Artist, Track, Genre, Decade
from backend.utils.tts_diagnostics import (
    get_missing_tts_info,
    get_decade_genre_ranking_summary
)

# 🪵 Logger setup
logger = logging.getLogger("supabase_summary")

# 🛣️ Create the router
router = APIRouter(
    prefix="/supabase",
    tags=["Supabase Summary"]
)
@router.get("/summary")
def get_summary(db_name: str = Query(...), db: Session = Depends(get_db)):
    logger.info(f"🔍 Generating DB summary for: {db_name}")
    try:
        return {
            "database": db_name,
            "tables": {
                "artists": len(db.exec(select(Artist)).all()),
                "tracks": len(db.exec(select(Track)).all()),
                "genres": len(db.exec(select(Genre)).all()),
                "decades": len(db.exec(select(Decade)).all())
            }
        }
    except Exception as e:
        logger.error(f"❌ Failed to summarize DB: {e}")
        return {"error": str(e)}

# 🧠 TTS diagnostics summary
@router.get("/tts/diagnostics")
def run_diagnostics(
    db: Session = Depends(get_db),
    show_samples: bool = Query(default=False, description="Include sample missing entries")
):
    result = get_missing_tts_info(db)
    ranking_summary = get_decade_genre_ranking_summary(db)

    response = {
        "summary": {
            "missing_text": {
                "track_detail": len(result["missing_text"]["track_detail"]),
                "artist_description": len(result["missing_text"]["artist_description"]),
                "ranking_intro": len(result["missing_text"]["ranking_intro"]),
            },
            "missing_mp3": {
                "track_intro": len(result["missing_mp3"]["track_intro"]),
                "track_detail": len(result["missing_mp3"]["track_detail"]),
                "artist_description": len(result["missing_mp3"]["artist_description"]),
            }
        },
        "ranking_summary": ranking_summary
    }

    if show_samples:
        response["samples"] = {
            "track_missing_intro_mp3": [t.track_name for t in result["missing_mp3"]["track_intro"][:5]],
            "track_missing_detail_mp3": [t.track_name for t in result["missing_mp3"]["track_detail"][:5]],
            "artist_missing_mp3": [a.name for a in result["missing_mp3"]["artist_description"][:5]],
        }

    return response

# 🧾 Full diagnostics (raw data for deep dive or dev use)
@router.get("/diagnostics")
def full_diagnostics(db: Session = Depends(get_db)):
    return {
        "missing_tts": get_missing_tts_info(db),
        "ranking_summary": get_decade_genre_ranking_summary(db)
    }
