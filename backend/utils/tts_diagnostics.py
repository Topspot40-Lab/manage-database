# backend/utils/tts_diagnostics.py

import re
import logging
import os
import time
import asyncio
import httpx
from sqlmodel import Session, select, func
from backend.models import Track, Artist, TrackRanking, DecadeGenre, Decade, Genre
from backend.config import (
    SUPABASE_URL,
    SUPABASE_SERVICE_ROLE_KEY,
    BUCKET_TRACK_INTRO,
    BUCKET_TRACK_DETAIL,
    BUCKET_ARTIST
)

logger = logging.getLogger("tts_diagnostics")

# ------------------------------------------------------------------------------
# 🧽 Normalize names for filenames (used in intro MP3 filenames)
# ------------------------------------------------------------------------------
def normalize_for_filename(text: str) -> str:
    return re.sub(r"[^\w]", "", text.lower().replace(" ", "_").replace("-", "_"))

# ------------------------------------------------------------------------------
# 🌐 Async check if a file exists in Supabase Storage
# ------------------------------------------------------------------------------
async def file_exists_async(bucket: str, path: str, client: httpx.AsyncClient) -> bool:
    try:
        url = f"{SUPABASE_URL}/storage/v1/object/info/{bucket}/{path}"
        headers = {
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            "apikey": SUPABASE_SERVICE_ROLE_KEY
        }
        response = await client.get(url, headers=headers, timeout=5.0)
        return response.status_code == 200
    except Exception as e:
        logger.warning(f"⚠️ Failed to check {bucket}/{path}: {e}")
        return False

# ------------------------------------------------------------------------------
# 🧩 Helper function to measure time and log a labeled async task
# ------------------------------------------------------------------------------
async def measure_and_log(label: str, func):
    logger.debug(f"🔍 Starting check: {label}")
    start = time.time()
    result = await func()
    duration = time.time() - start
    logger.info(f"⏱️ {label} check completed in {duration:.2f} seconds")
    return result

# ------------------------------------------------------------------------------
# 🎧 Check for missing intro MP3s
# ------------------------------------------------------------------------------
async def check_intro_mp3s(db: Session, client: httpx.AsyncClient):
    stmt = (
        select(TrackRanking, Decade.decade_name, Genre.genre_name)
        .join(DecadeGenre, TrackRanking.decade_genre_id == DecadeGenre.id)
        .join(Decade, DecadeGenre.decade_id == Decade.id)
        .join(Genre, DecadeGenre.genre_id == Genre.id)
    )
    result = db.exec(stmt).all()

    # Prepare filename keys and missing text entries
    intro_keys = []
    text_missing_entries = []

    for ranking, decade, genre in result:
        filename = f"{normalize_for_filename(decade)}_{normalize_for_filename(genre)}_{ranking.ranking:02}.mp3"
        intro_keys.append(filename)

        # Check for missing/empty/null text
        if not ranking.intro or ranking.intro.strip().lower() == "null":
            text_missing_entries.append(f"{ranking.ranking:02} — {decade}, {genre}")

    # Check missing MP3s
    intro_tasks = [file_exists_async(BUCKET_TRACK_INTRO, key, client) for key in intro_keys]
    results = await asyncio.gather(*intro_tasks)
    missing_mp3s = [key for key, exists in zip(intro_keys, results) if not exists]

    # Logging missing MP3s
    if missing_mp3s:
        logger.debug(f"🛑 {len(missing_mp3s)} intro MP3(s) missing out of {len(intro_keys)} total:")
        logger.debug("\n" + "\n".join(f"- {name}" for name in missing_mp3s[:15]))
    else:
        logger.debug("✅ All intro MP3s present — no missing files.")

    total_rankings = len(result)

    # Logging missing/empty intro texts
    if text_missing_entries:
        logger.debug(f"🛑 {len(text_missing_entries)} intro text(s) missing or invalid out of {total_rankings} total:")
        logger.debug("\n" + "\n".join(f"- Rank {entry}" for entry in text_missing_entries))
    else:
        logger.debug(f"✅ All {total_rankings} intro text fields present and valid.")

    return missing_mp3s

# ------------------------------------------------------------------------------
# 🎶 Check for missing detail MP3s
# ------------------------------------------------------------------------------
async def check_detail_mp3s(tracks, client: httpx.AsyncClient):
    detail_tracks = [t for t in tracks if t.spotify_track_id]

    # Check for missing or invalid detail text
    text_missing = [
        t for t in detail_tracks
        if not t.detail or t.detail.strip().lower() == "null"
    ]

    # Log missing/invalid detail text fields
    total_tracks = len(detail_tracks)
    if text_missing:
        logger.debug(f"🛑 {len(text_missing)} detail text(s) missing or invalid out of {total_tracks} total:")
        logger.debug("\n" + "\n".join(f"- {t.track_name} ({t.spotify_track_id})" for t in text_missing))
    else:
        logger.debug(f"✅ All {total_tracks} detail text fields present and valid.")

    # Now check for missing detail MP3s
    detail_tasks = [
        file_exists_async(BUCKET_TRACK_DETAIL, f"{t.spotify_track_id}.mp3", client)
        for t in detail_tracks
    ]
    results = await asyncio.gather(*detail_tasks)

    missing = [t for t, exists in zip(detail_tracks, results) if not exists]
    if missing:
        logger.debug(f"🛑 {len(missing)} detail MP3(s) missing:\n" +
                     "\n".join(f"- title: {t.track_name.ljust(30)} artist: {t.artist_display_name or '[unknown]'}"
                               for t in missing))

    else:
        logger.debug("✅ All detail MP3s present — no missing files.")

    logger.debug(f"🎶 Detail MP3s checked: {len(results)}, missing: {len(missing)}")

    return missing


# ------------------------------------------------------------------------------
# 🎤 Check for missing artist MP3s
# ------------------------------------------------------------------------------
async def check_artist_mp3s(artists, client: httpx.AsyncClient):
    artist_list = [a for a in artists if a.spotify_artist_id]

    # 🔤 Check for missing or invalid artist_description
    text_missing = [
        a for a in artist_list
        if not a.artist_description or a.artist_description.strip().lower() in {"", "null"}
    ]

    total_artists = len(artist_list)

    if text_missing:
        logger.debug(f"🛑 {len(text_missing)} artist description(s) missing or invalid out of {total_artists} total:")
        logger.debug("\n" + "\n".join(f"- name: {a.artist_name:<30}  spotify_id: {a.spotify_artist_id}" for a in text_missing))
    else:
        logger.debug(f"✅ All {total_artists} artist description fields present and valid.")

    # 🔈 Check for missing artist MP3s
    artist_tasks = [
        file_exists_async(BUCKET_ARTIST, f"{a.spotify_artist_id}.mp3", client)
        for a in artist_list
    ]
    results = await asyncio.gather(*artist_tasks)

    missing = [a for a, exists in zip(artist_list, results) if not exists]

    if missing:
        logger.debug(f"🛑 {len(missing)} artist MP3(s) missing:\n" +
                     "\n".join(f"- name: {a.artist_name:<30}  spotify_id: {a.spotify_artist_id}" for a in missing))
    else:
        logger.debug("✅ All artist MP3s present — no missing files.")

    logger.debug(f"🎤 Artist MP3s checked: {len(results)}, missing: {len(missing)}")
    return missing

# ------------------------------------------------------------------------------
# 🔍 Master diagnostic function to gather all missing TTS data
# ------------------------------------------------------------------------------
async def get_missing_tts_info(
    db: Session,
    check_intro_mp3: bool = False,
    check_detail_mp3: bool = False,
    check_artist_mp3: bool = False
):
    # Load records from DB
    tracks = db.exec(select(Track)).all()
    artists = db.exec(select(Artist)).all()
    rankings = db.exec(select(TrackRanking)).all()

    # 🔤 Check for missing TEXT fields
    missing_detail_text = [t for t in tracks if not t.detail or not t.detail.strip()]
    missing_artist_desc = [a for a in artists if not a.artist_description or not a.artist_description.strip()]
    missing_intro_text = [r for r in rankings if not r.intro or not r.intro.strip()]

    # 🔈 Check for missing MP3s (optional and async)
    missing_intro_mp3 = []
    missing_detail_mp3 = []
    missing_artist_mp3 = []

    async with httpx.AsyncClient() as client:
        if check_intro_mp3:
            missing_intro_mp3 = await measure_and_log("Intro MP3s", lambda: check_intro_mp3s(db, client))

        if check_detail_mp3:
            missing_detail_mp3 = await measure_and_log("Detail MP3s", lambda: check_detail_mp3s(tracks, client))

        if check_artist_mp3:
            missing_artist_mp3 = await measure_and_log("Artist MP3s", lambda: check_artist_mp3s(artists, client))

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

# ------------------------------------------------------------------------------
# 📊 Utility: summary of decade-genre combinations with ranking counts
# ------------------------------------------------------------------------------
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

# ------------------------------------------------------------------------------
# 🔐 Exported functions
# ------------------------------------------------------------------------------
__all__ = [
    "get_missing_tts_info",
    "get_decade_genre_ranking_summary",
    "normalize_for_filename",  # ✅ Add this line
]

