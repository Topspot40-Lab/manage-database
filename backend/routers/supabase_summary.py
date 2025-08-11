from fastapi import APIRouter, Query, Depends
from sqlmodel import Session, select
import logging
from sqlalchemy import func
from backend.models import Artist, Track, Genre, Decade, DecadeGenre, TrackRanking

from backend.database import get_db
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
def get_summary(
    db_name: str = Query("topspot40-dev"),
    db: Session = Depends(get_db)
):
    logger.info(f"🔍 Generating DB summary for: {db_name}")

    try:
        # Table counts (return int)
        artists_count = db.exec(select(func.count(Artist.id))).first()
        tracks_count = db.exec(select(func.count(Track.id))).first()
        genres_count = db.exec(select(func.count(Genre.id))).first()
        decades_count = db.exec(select(func.count(Decade.id))).first()
        rankings_count = db.exec(select(func.count(TrackRanking.id))).first()

        summary = {
            "database": db_name,
            "tables": {
                "artists": artists_count,
                "tracks": tracks_count,
                "genres": genres_count,
                "decades": decades_count,
                "track_rankings": rankings_count
            },
            "ranking_counts": []
        }

        # Ranked track breakdown by decade and genre
        result = db.exec(
            select(
                Decade.name,
                Genre.name,
                func.count(TrackRanking.id)
            )
            .join(DecadeGenre, TrackRanking.decade_genre_id == DecadeGenre.id)
            .join(Decade, Decade.id == DecadeGenre.decade_id)
            .join(Genre, Genre.id == DecadeGenre.genre_id)
            .group_by(Decade.name, Genre.name)
            .order_by(Decade.name, Genre.name)
        ).all()

        for decade_name, genre_name, count in result:
            logger.info(f"📊 {decade_name} / {genre_name} → {count} ranked track(s)")
            summary["ranking_counts"].append({
                "decade": decade_name,
                "genre": genre_name,
                "count": count
            })

        return summary

    except Exception as e:
        logger.error(f"❌ Failed to summarize DB: {e}")
        return {"error": str(e)}


@router.get("/tts/diagnostics")
async def run_diagnostics(
        db: Session = Depends(get_db),
        show_samples: bool = Query(False, description="Include sample missing entries"),
        check_intro_mp3: bool = Query(False, description="Check for missing intro MP3 files (TrackRanking.intro)"),
        check_specialty_intro_mp3: bool = Query(False,
                                                description="Check for missing specialty intro MP3 files (SpecialtyRanking.intro)"),
        check_detail_mp3: bool = Query(False, description="Check for missing detail MP3 files (Track.detail)"),
        check_artist_mp3: bool = Query(False, description="Check for missing artist MP3 files (Artist.description)"),

):
    logger.info(
        "🧠 Starting TTS diagnostics summary... | "
        f"show_samples={show_samples}, "
        f"check_intro_mp3={check_intro_mp3}, "
        f"check_detail_mp3={check_detail_mp3}, "
        f"check_artist_mp3={check_artist_mp3}, "
        f"check_specialty_intro_mp3={check_specialty_intro_mp3}"
    )

    result = await get_missing_tts_info(
        db,
        check_intro_mp3=check_intro_mp3,
        check_detail_mp3=check_detail_mp3,
        check_artist_mp3=check_artist_mp3,
        check_specialty_intro_mp3=check_specialty_intro_mp3,  # 👈 new
    )
    ranking_summary = get_decade_genre_ranking_summary(db)

    summary = {"missing_text": {}, "missing_mp3": {}}

    # Text counts (unchanged)
    missing_text = result.get("missing_text", {})
    if "track_detail" in missing_text:
        summary["missing_text"]["track_detail"] = len(missing_text["track_detail"])
    if "artist_description" in missing_text:
        summary["missing_text"]["artist_description"] = len(missing_text["artist_description"])
    if "ranking_intro" in missing_text:
        summary["missing_text"]["ranking_intro"] = len(missing_text["ranking_intro"])

    # MP3 counts (add specialty)
    missing_mp3 = result.get("missing_mp3", {})
    if check_intro_mp3 and "track_intro" in missing_mp3:
        summary["missing_mp3"]["track_intro"] = len(missing_mp3["track_intro"])
    if check_detail_mp3 and "track_detail" in missing_mp3:
        summary["missing_mp3"]["track_detail"] = len(missing_mp3["track_detail"])
    if check_artist_mp3 and "artist_description" in missing_mp3:
        summary["missing_mp3"]["artist_description"] = len(missing_mp3["artist_description"])
    if check_specialty_intro_mp3 and "specialty_intro" in missing_mp3:  # 👈 new
        summary["missing_mp3"]["specialty_intro"] = len(missing_mp3["specialty_intro"])

    response = {
        "summary": summary,
        "ranking_summary": ranking_summary
    }

    if show_samples:
        samples = {}

        if check_intro_mp3 and "track_intro" in missing_mp3:
            samples["track_missing_intro_mp3"] = [
                getattr(t, "track_name", None) or getattr(getattr(t, "track", None), "track_name", "(unknown)") for t in
                missing_mp3["track_intro"][:5]]

        if check_detail_mp3 and "track_detail" in missing_mp3:
            samples["track_missing_detail_mp3"] = [
                getattr(t, "track_name", None) or getattr(getattr(t, "track", None), "track_name", "(unknown)") for t in
                missing_mp3["track_detail"][:5]]

        if check_artist_mp3 and "artist_description" in missing_mp3:
            samples["artist_missing_mp3"] = [getattr(a, "name", None) or getattr(a, "artist_name", "(unknown)") for a in
                                             missing_mp3["artist_description"][:5]]

        # 👇 NEW: sample names for specialty intros
        if check_specialty_intro_mp3 and "specialty_intro" in missing_mp3:
            samples["specialty_missing_intro_mp3"] = [
                # Try SpecialtyRanking.track.track_name → fallback to .track_name or "(unknown)"
                getattr(sr, "track_name", None)
                or getattr(getattr(sr, "track", None), "track_name", "(unknown)")
                for sr in missing_mp3["specialty_intro"][:5]
            ]

        response["samples"] = samples

    return response


# 🧾 Full diagnostics (raw data for deep dive or dev use)
@router.get("/diagnostics")
def full_diagnostics(db: Session = Depends(get_db)):
    return {
        "missing_tts": get_missing_tts_info(db),
        "ranking_summary": get_decade_genre_ranking_summary(db)
    }
