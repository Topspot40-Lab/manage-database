from fastapi import APIRouter, Query, Depends
from sqlmodel import Session, select
from sqlalchemy import func
import logging
from typing import Literal  # optional DX improvement

from backend.models import Artist, Track, Genre, Decade, DecadeGenre, TrackRanking
from backend.database import get_db
from backend.utils.tts_diagnostics import (
    get_missing_tts_info,
    get_decade_genre_ranking_summary
)

logger = logging.getLogger("supabase_summary")

router = APIRouter(prefix="/supabase", tags=["Supabase Summary"])

def _canon_lang(code: str) -> str:
    m = (code or "en").strip().lower()
    return {"en": "en", "es": "es", "ptbr": "pt-BR"}.get(m, "en")
@router.get("/summary")
def get_summary(
    db_name: str = Query("topspot40-dev"),
    db: Session = Depends(get_db)
):
    logger.info(f"🔍 Generating DB summary for: {db_name}")

    try:
        # COUNT(*) always returns exactly one row
        def _count(count_stmt) -> int:
            return int(db.exec(count_stmt).one())

        artists_count  = _count(select(func.count(Artist.id)))
        tracks_count   = _count(select(func.count(Track.id)))
        genres_count   = _count(select(func.count(Genre.id)))
        decades_count  = _count(select(func.count(Decade.id)))
        rankings_count = _count(select(func.count(TrackRanking.id)))

        # Ranked track breakdown by decade and genre
        breakdown_stmt = (
            select(
                Decade.decade_name,
                Genre.genre_name,
                func.count(TrackRanking.id),
            )
            .select_from(TrackRanking)
            .join(DecadeGenre, TrackRanking.decade_genre_id == DecadeGenre.id)
            .join(Decade, Decade.id == DecadeGenre.decade_id)
            .join(Genre,  Genre.id  == DecadeGenre.genre_id)
            .group_by(Decade.decade_name, Genre.genre_name)
            .order_by(Decade.decade_name, Genre.genre_name)
        )
        rows = db.exec(breakdown_stmt).all()

        return {
            "database": db_name,
            "tables": {
                "artists": artists_count,
                "tracks": tracks_count,
                "genres": genres_count,
                "decades": decades_count,
                "track_rankings": rankings_count,
            },
            "ranking_counts": [
                {"decade": d, "genre": g, "count": c} for (d, g, c) in rows
            ],
        }

    except Exception as e:
        logger.exception("❌ Failed to summarize DB")
        return {"error": str(e)}

@router.get("/tts/diagnostics")
async def run_diagnostics(
    db: Session = Depends(get_db),
    # If you prefer stricter typing in docs/IDE, change type to Literal["en","es","ptbr"]
    check_tts_language: Literal["en", "es", "ptbr"] = Query(
        "en",
        description='Language to check MP3s in: "en", "es", or "ptbr"',
    ),
    check_intro_mp3: bool = Query(False, description="Check for missing intro MP3 files"),
    check_detail_mp3: bool = Query(False, description="Check for missing detail MP3 files"),
    check_artist_mp3: bool = Query(False, description="Check for missing artist MP3 files"),
    show_samples: bool = Query(False, description="Include sample missing entries"),
    check_decade_genre_summary: bool = Query(
        False, description="Include the final decade/genre ranking summary table"
    ),
):
    lang = _canon_lang(check_tts_language)
    logger.info(
        "🧠 TTS diagnostics | samples=%s intro=%s detail=%s artist=%s lang=%s summary=%s",
        show_samples, check_intro_mp3, check_detail_mp3, check_artist_mp3, lang, check_decade_genre_summary
    )

    result = await get_missing_tts_info(
        db,
        check_intro_mp3=check_intro_mp3,
        check_detail_mp3=check_detail_mp3,
        check_artist_mp3=check_artist_mp3,
        language=lang,
    )

    summary = {"missing_text": {}, "missing_mp3": {}}
    missing_text = result.get("missing_text", {})
    if "track_detail" in missing_text:
        summary["missing_text"]["track_detail"] = len(missing_text["track_detail"])
    if "artist_description" in missing_text:
        summary["missing_text"]["artist_description"] = len(missing_text["artist_description"])
    if "ranking_intro" in missing_text:
        summary["missing_text"]["ranking_intro"] = len(missing_text["ranking_intro"])

    missing_mp3 = result.get("missing_mp3", {})
    if check_intro_mp3 and "track_intro" in missing_mp3:
        summary["missing_mp3"]["track_intro"] = len(missing_mp3["track_intro"])
    if check_detail_mp3 and "track_detail" in missing_mp3:
        summary["missing_mp3"]["track_detail"] = len(missing_mp3["track_detail"])
    if check_artist_mp3 and "artist_mp3" in missing_mp3:
        summary["missing_mp3"]["artist_mp3"] = len(missing_mp3["artist_mp3"])

    response = {
        "params": {
            "language": lang,
            "include_ranking_summary": check_decade_genre_summary,
            "show_samples": show_samples,
        },
        "summary": summary,
    }

    if check_decade_genre_summary:
        response["ranking_summary"] = get_decade_genre_ranking_summary(db)

    if show_samples:
        samples = {}
        if check_intro_mp3 and "track_intro" in missing_mp3:
            samples["track_missing_intro_mp3"] = missing_mp3["track_intro"][:5]
        if check_detail_mp3 and "track_detail" in missing_mp3:
            samples["track_missing_detail_mp3"] = [t.track_name for t in missing_mp3["track_detail"][:5]]
        if check_artist_mp3 and "artist_mp3" in missing_mp3:
            samples["artist_missing_mp3"] = [a.artist_name for a in missing_mp3["artist_mp3"][:5]]
        response["samples"] = samples

    return response

# 🧾 Full diagnostics (raw data for deep dive or dev use)
@router.get("/diagnostics")
async def full_diagnostics(db: Session = Depends(get_db)):
    return {
        "missing_tts": await get_missing_tts_info(db),
        "ranking_summary": get_decade_genre_ranking_summary(db),
    }
