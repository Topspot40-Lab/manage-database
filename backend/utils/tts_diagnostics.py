from fastapi import APIRouter, Depends
from sqlmodel import Session, select, func
import os
import logging

from backend.database import get_db
from backend.models import (
    Track, Artist, TrackRanking, DecadeGenre, Decade, Genre
)
from supabase import create_client

# 🪵 Logger
logger = logging.getLogger("tts_diagnostics")

# 📦 Supabase setup
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

# 🚀 Supabase bucket constants (must use dash-case, not underscores)
BUCKET_TRACK_INTRO = "track-intro-mp3-files"
BUCKET_TRACK_DETAIL = "track-detail-mp3-files"
BUCKET_ARTIST = "artist-mp3-files"

# 🚦 FastAPI Router
router = APIRouter(
    prefix="/supabase",
    tags=["Supabase Summary"]
)

def file_exists(bucket: str, path: str) -> bool:
    try:
        directory = path.rsplit("/", 1)[0]
        filename = path.rsplit("/", 1)[-1]
        files = supabase.storage.from_(bucket).list(path=directory)
        return any(f["name"] == filename for f in files)
    except Exception as e:
        logger.warning(f"⚠️ Failed to check {bucket}/{path}: {e}")
        return False


def get_missing_tts_info(db: Session):
    tracks = db.exec(select(Track)).all()
    artists = db.exec(select(Artist)).all()
    rankings = db.exec(select(TrackRanking)).all()

    missing_detail_text = []
    missing_intro_mp3 = []
    missing_detail_mp3 = []

    for t in tracks:
        sid = t.spotify_track_id
        if not t.detail or not t.detail.strip():
            missing_detail_text.append(t)
        if sid:
            if not file_exists(BUCKET_TRACK_INTRO, f"{sid}.mp3"):
                missing_intro_mp3.append(t)
            if not file_exists(BUCKET_TRACK_DETAIL, f"{sid}.mp3"):
                missing_detail_mp3.append(t)

    missing_artist_desc = []
    missing_artist_mp3 = []
    for a in artists:
        if not a.artist_description or not a.artist_description.strip():
            missing_artist_desc.append(a)
        if a.spotify_artist_id:
            if not file_exists(BUCKET_ARTIST, f"{a.spotify_artist_id}.mp3"):
                missing_artist_mp3.append(a)

    missing_intro_text = []
    for r in rankings:
        if not r.intro or not r.intro.strip():
            missing_intro_text.append(r)

    logger.info(
        "\n📊 Missing TTS Summary:\n"
        f"   🧾 Track detail text missing .... {len(missing_detail_text):3d}\n"
        f"   🎙️ Track intro MP3 missing ...... {len(missing_intro_mp3):3d}\n"
        f"   🎙️ Track detail MP3 missing ..... {len(missing_detail_mp3):3d}\n"
        f"   👤 Artist description missing ... {len(missing_artist_desc):3d}\n"
        f"   🎧 Artist MP3 missing ........... {len(missing_artist_mp3):3d}\n"
        f"   🏆 Ranking intro missing ........ {len(missing_intro_text):3d}"
    )

    return {
        "missing_text": {
            "track_detail": missing_detail_text,
            "artist_description": missing_artist_desc,
            "ranking_intro": missing_intro_text
        },
        "missing_mp3": {
            "track_intro": missing_intro_mp3,
            "track_detail": missing_detail_mp3,
            "artist_description": missing_artist_mp3
        }
    }


def get_decade_genre_ranking_summary(db: Session):
    logger.info("📊 Building ranking summary per decade-genre...")

    stmt = (
        select(
            DecadeGenre.id,
            Decade.decade_name,
            Genre.genre_name,
            func.count(TrackRanking.id).label("ranking_count")
        )
        .join(Decade, DecadeGenre.decade_id == Decade.id)
        .join(Genre, DecadeGenre.genre_id == Genre.id)
        .join(TrackRanking, TrackRanking.decade_genre_id == DecadeGenre.id)
        .group_by(DecadeGenre.id, Decade.decade_name, Genre.genre_name)
        .order_by(Decade.decade_name, Genre.genre_name)
    )

    results = db.exec(stmt).all()

    summary = []
    for id, decade, genre, count in results:
        summary.append({
            "decade_genre_id": id,
            "decade": decade,
            "genre": genre,
            "ranking_count": count
        })

    logger.info(f"✅ Found {len(summary)} unique decade-genre combos.")
    return summary


@router.get("/tts/diagnostics")
def run_diagnostics(db: Session = Depends(get_db)):
    result = get_missing_tts_info(db)
    ranking_summary = get_decade_genre_ranking_summary(db)

    return {
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
        "samples": {
            "track_missing_intro": [t.track_name for t in result["missing_text"]["track_detail"][:5]],
            "artist_missing_description": [a.name for a in result["missing_text"]["artist_description"][:5]],
            "ranking_missing_info": [f"{r.track_name} (rank {r.rank})" for r in result["missing_text"]["ranking_intro"][:5]],
            "missing_intro_mp3": [t.track_name for t in result["missing_mp3"]["track_intro"][:5]],
            "missing_detail_mp3": [t.track_name for t in result["missing_mp3"]["track_detail"][:5]],
            "missing_artist_mp3": [a.name for a in result["missing_mp3"]["artist_description"][:5]]
        },
        "ranking_summary": ranking_summary
    }


__all__ = ["get_missing_tts_info", "get_decade_genre_ranking_summary"]
