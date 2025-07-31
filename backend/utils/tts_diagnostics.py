from sqlmodel import Session, select
from backend.models import Track, Artist, TrackRanking
from supabase import create_client
import os
import logging

logger = logging.getLogger("tts_diagnostics")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

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

    # Track fields
    missing_intro_text = []
    missing_detail_text = []
    missing_intro_mp3 = []
    missing_detail_mp3 = []

    for t in tracks:
        sid = t.spotify_track_id
        if not t.intro or not t.intro.strip():
            missing_intro_text.append(t)
        if not t.detail or not t.detail.strip():
            missing_detail_text.append(t)
        if sid:
            if not file_exists("track_intro_mp3_files", f"{sid}.mp3"):
                missing_intro_mp3.append(t)
            if not file_exists("track_detail_mp3_files", f"{sid}.mp3"):
                missing_detail_mp3.append(t)

    # Artist fields
    missing_artist_desc = []
    missing_artist_mp3 = []
    for a in artists:
        if not a.description or not a.description.strip():
            missing_artist_desc.append(a)
        if a.spotify_artist_id:
            if not file_exists("artist_mp3_files", f"{a.spotify_artist_id}.mp3"):
                missing_artist_mp3.append(a)

    # Ranking info field
    missing_info_text = []
    for r in rankings:
        if not r.info or not r.info.strip():
            missing_info_text.append(r)

    return {
        "missing_text": {
            "track_intro": missing_intro_text,
            "track_detail": missing_detail_text,
            "artist_description": missing_artist_desc,
            "ranking_info": missing_info_text
        },
        "missing_mp3": {
            "track_intro": missing_intro_mp3,
            "track_detail": missing_detail_mp3,
            "artist_description": missing_artist_mp3
        }
    }

