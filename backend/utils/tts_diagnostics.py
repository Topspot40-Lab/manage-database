# backend/utils/tts_diagnostics.py

import logging
import os
import time
from sqlmodel import Session, select, func
from backend.models import Track, Artist, TrackRanking, DecadeGenre, Decade, Genre

logger = logging.getLogger("tts_diagnostics")

# Supabase creds
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# Buckets
BUCKET_TRACK_INTRO = "track-intro-mp3-files"
BUCKET_TRACK_DETAIL = "track-detail-mp3-files"
BUCKET_ARTIST = "artist-mp3-files"

import httpx
import asyncio
from backend.config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

async def file_exists_async(bucket: str, path: str, client: httpx.AsyncClient) -> bool:
    try:
        url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{path}"
        headers = {"Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"}
        response = await client.head(url, headers=headers, timeout=5.0)
        return response.status_code == 200
    except Exception as e:
        logger.warning(f"⚠️ Failed to check {bucket}/{path}: {e}")
        return False


async def get_missing_tts_info(
    db: Session,
    check_intro_mp3: bool = False,
    check_detail_mp3: bool = False,
    check_artist_mp3: bool = False
):
    tracks = db.exec(select(Track)).all()
    artists = db.exec(select(Artist)).all()
    rankings = db.exec(select(TrackRanking)).all()

    missing_detail_text = [t for t in tracks if not t.detail or not t.detail.strip()]
    missing_artist_desc = [a for a in artists if not a.artist_description or not a.artist_description.strip()]
    missing_intro_text = [r for r in rankings if not r.intro or not r.intro.strip()]

    missing_intro_mp3 = []
    missing_detail_mp3 = []
    missing_artist_mp3 = []

    async with httpx.AsyncClient() as client:
        if check_intro_mp3:
            logger.debug("🎧 Starting check: intro MP3s (from track_ranking)")

            stmt = (
                select(TrackRanking, Decade.decade_name, Genre.genre_name)
                .join(DecadeGenre, TrackRanking.decade_genre_id == DecadeGenre.id)
                .join(Decade, DecadeGenre.decade_id == Decade.id)
                .join(Genre, DecadeGenre.genre_id == Genre.id)
            )

            result = db.exec(stmt).all()

            # 🎧 Construct MP3 filenames based on ranking data
            intro_keys = [
                f"{decade}_{genre}_{getattr(ranking, 'ranking', 0):02}.mp3"
                for ranking, decade, genre in result
            ]

            logger.debug(f"🎧 Total track_ranking entries to check: {len(intro_keys)}")

            intro_tasks = [
                file_exists_async(BUCKET_TRACK_INTRO, file_key, client)
                for file_key in intro_keys
            ]
            intro_results = await asyncio.gather(*intro_tasks)

            missing_intro_mp3 = [file_key for file_key, exists in zip(intro_keys, intro_results) if not exists]

            logger.debug(f"🎧 Intro MP3s missing: {len(missing_intro_mp3)}")

            if missing_intro_mp3:
                logger.debug(f"📂 Missing intro examples: {missing_intro_mp3[:5]}")

        if check_detail_mp3:
            logger.debug("🎶 Starting check: detail MP3s")
            start = time.time()

            detail_tracks = [t for t in tracks if t.spotify_track_id]
            detail_tasks = [
                file_exists_async(BUCKET_TRACK_DETAIL, f"{t.spotify_track_id}.mp3", client)
                for t in detail_tracks
            ]
            detail_results = await asyncio.gather(*detail_tasks)
            missing_detail_mp3 = [t for t, exists in zip(detail_tracks, detail_results) if not exists]

            for file_key in missing_intro_mp3[:5]:
                logger.debug(f"❌ Missing intro MP3 for: {file_key}")

            duration = time.time() - start
            logger.info(f"⏱️ Detail MP3 check completed in {duration:.2f} seconds")
            logger.debug(f"🎶 Detail MP3s checked: {len(detail_results)}, missing: {len(missing_detail_mp3)}")

        if check_artist_mp3:
            logger.debug("🎤 Starting check: artist MP3s")
            start = time.time()

            artist_list = [a for a in artists if a.spotify_artist_id]
            artist_tasks = [
                file_exists_async(BUCKET_ARTIST, f"{a.spotify_artist_id}.mp3", client)
                for a in artist_list
            ]
            artist_results = await asyncio.gather(*artist_tasks)
            missing_artist_mp3 = [a for a, exists in zip(artist_list, artist_results) if not exists]

            duration = time.time() - start
            logger.info(f"⏱️ Artist MP3 check completed in {duration:.2f} seconds")
            logger.debug(f"🎤 Artist MP3s checked: {len(artist_results)}, missing: {len(missing_artist_mp3)}")

    return {
        "missing_text": {
            "track_detail": missing_detail_text,
            "artist_description": missing_artist_desc,
            "ranking_intro": missing_intro_text,
        },
        "missing_mp3": {
            "track_intro": missing_intro_mp3,
            "track_detail": missing_detail_mp3,
            "artist_description": missing_artist_mp3,
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

__all__ = ["get_missing_tts_info", "get_decade_genre_ranking_summary"]
