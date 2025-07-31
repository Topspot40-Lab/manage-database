from fastapi import APIRouter, Query, Depends
from sqlmodel import Session, select
import logging
from backend.utils.tts_diagnostics import get_missing_tts_info

# 🧩 Import your database session and models
from backend.database import get_db
from backend.models import Artist, Track, Genre, Decade  # Add more models if needed

# 🪵 Logger setup
logger = logging.getLogger("supabase_summary")

# 🛣️ Create the router
router = APIRouter(
    prefix="/supabase",
    tags=["Supabase Summary"]
)


# 🚀 Define the endpoint
@router.get("/summary")
def get_summary(db_name: str = Query(...), db: Session = Depends(get_db)):
    logger.info(f"🔍 Generating DB summary for: {db_name}")

    try:
        artist_count = db.exec(select(Artist)).all()
        track_count = db.exec(select(Track)).all()
        genre_count = db.exec(select(Genre)).all()
        decade_count = db.exec(select(Decade)).all()

        return {
            "database": db_name,
            "tables": {
                "artists": len(artist_count),
                "tracks": len(track_count),
                "genres": len(genre_count),
                "decades": len(decade_count)
            }
        }

    except Exception as e:
        logger.error(f"❌ Failed to summarize DB: {e}")
        return {"error": str(e)}



@router.get("/tts/diagnostics")
def run_diagnostics(db: Session = Depends(get_db)):
    result = get_missing_tts_info(db)

    return {
        "summary": {
            "missing_text": {
                "track_intro": len(result["missing_text"]["track_intro"]),
                "track_detail": len(result["missing_text"]["track_detail"]),
                "artist_description": len(result["missing_text"]["artist_description"]),
                "ranking_info": len(result["missing_text"]["ranking_info"]),
            },
            "missing_mp3": {
                "track_intro": len(result["missing_mp3"]["track_intro"]),
                "track_detail": len(result["missing_mp3"]["track_detail"]),
                "artist_description": len(result["missing_mp3"]["artist_description"]),
            }
        },
        "samples": {
            "track_missing_intro": [t.track_name for t in result["missing_text"]["track_intro"][:5]],
            "track_missing_detail": [t.track_name for t in result["missing_text"]["track_detail"][:5]],
            "artist_missing_description": [a.name for a in result["missing_text"]["artist_description"][:5]],
            "ranking_missing_info": [f"{r.track_name} (rank {r.rank})" for r in result["missing_text"]["ranking_info"][:5]],
            "missing_intro_mp3": [t.track_name for t in result["missing_mp3"]["track_intro"][:5]],
            "missing_detail_mp3": [t.track_name for t in result["missing_mp3"]["track_detail"][:5]],
            "missing_artist_mp3": [a.name for a in result["missing_mp3"]["artist_description"][:5]]
        }
    }