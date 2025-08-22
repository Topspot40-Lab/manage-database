# backend/utils/tts_diagnostics.py

import re
import logging
import time
import asyncio
import httpx
from sqlmodel import Session, select, func
from backend.models import Track, Artist, TrackRanking, DecadeGenre, Decade, Genre
# NEW
from backend.config import (
    SUPABASE_URL,
    SUPABASE_SERVICE_ROLE_KEY,
    BUCKETS,
    AUDIO_PREFIXES,
    DEFAULT_TTS_LANGUAGE,
)

logger = logging.getLogger("tts_diagnostics")

def _bucket_for(lang: str, kind: str) -> str:
    """Return the correct language-scoped bucket for intro/detail/artist."""
    lang_map = BUCKETS.get(lang) or BUCKETS[DEFAULT_TTS_LANGUAGE]
    return lang_map[kind]

def _prefixed_key(kind: str, filename: str) -> str:
    """Build 'intro/filename.mp3', 'detail/ID.mp3', etc."""
    return f"{AUDIO_PREFIXES[kind]}/{filename}"

# ------------------------------------------------------------------------------
# 🧽 Normalize names for filenames (used in intro MP3 filenames)
# ------------------------------------------------------------------------------
def normalize_for_filename(text: str) -> str:
    return re.sub(r"\W", "", text.lower().replace(" ", "_").replace("-", "_"))

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
async def measure_and_log(label: str, check_func):
    logger.debug(f"🔍 Starting check: {label}")
    start = time.time()
    result = await check_func()
    duration = time.time() - start
    logger.debug(f"⏱️ {label} check completed in {duration:.2f} seconds")
    return result

# ------------------------------------------------------------------------------
# 🎧 Check for missing intro MP3s
# ------------------------------------------------------------------------------
# 🎧 Check for missing intro MP3s
async def check_intro_mp3s(db: Session, client: httpx.AsyncClient, *, language: str = DEFAULT_TTS_LANGUAGE):
    stmt = (
        select(TrackRanking, Decade.decade_name, Genre.genre_name)
        .join(DecadeGenre, TrackRanking.decade_genre_id == DecadeGenre.id)
        .join(Decade, DecadeGenre.decade_id == Decade.id)
        .join(Genre, DecadeGenre.genre_id == Genre.id)
    )
    result = db.exec(stmt).all()

    intro_bucket = _bucket_for(language, "intro")

    # Prepare filename keys and missing text entries
    intro_keys = []
    text_missing_entries = []

    for ranking, decade, genre in result:
        filename = f"{normalize_for_filename(decade)}_{normalize_for_filename(genre)}_{ranking.ranking:02}.mp3"
        intro_keys.append(_prefixed_key("intro", filename))

        # Check for missing/empty/null text
        if not ranking.intro or ranking.intro.strip().lower() == "null":
            text_missing_entries.append(f"{ranking.ranking:02} — {decade}, {genre}")

    # Check missing MP3s (language-scoped bucket + intro/ prefix)
    intro_tasks = [file_exists_async(intro_bucket, key, client) for key in intro_keys]
    results = await asyncio.gather(*intro_tasks)
    missing_mp3s = [key for key, exists in zip(intro_keys, results) if not exists]

    # Logging missing MP3s
    if missing_mp3s:
        logger.info(f"🛑 {len(missing_mp3s)} intro MP3(s) missing out of {len(intro_keys)} total:")
        logger.debug("\n" + "\n".join(f"- {name}" for name in missing_mp3s[:100]))
    else:
        logger.info("✅ All intro MP3s present — no missing files.")

    total_rankings = len(result)

    # Logging missing/empty intro texts
    if text_missing_entries:
        logger.info(f"🛑 {len(text_missing_entries)} intro text(s) missing or invalid out of {total_rankings} total:")
        logger.debug("\n" + "\n".join(f"- Rank {entry}" for entry in text_missing_entries))
    else:
        logger.info(f"✅ All {total_rankings} intro text fields present and valid.")

    return missing_mp3s

# ------------------------------------------------------------------------------
# 🎶 Check for missing detail MP3s
# ------------------------------------------------------------------------------
# 🎶 Check for missing detail MP3s
async def check_detail_mp3s(tracks, client: httpx.AsyncClient, *, language: str = DEFAULT_TTS_LANGUAGE):
    detail_tracks = [t for t in tracks if t.spotify_track_id]

    # Check for missing or invalid detail text
    text_missing = [
        t for t in detail_tracks
        if not t.detail or t.detail.strip().lower() == "null"
    ]

    total_tracks = len(detail_tracks)
    if text_missing:
        logger.info(f"🛑 {len(text_missing)} detail text(s) missing or invalid out of {total_tracks} total:")
        logger.debug("\n" + "\n".join(f"- {t.track_name} ({t.spotify_track_id})" for t in text_missing))
    else:
        logger.info(f"✅ All {total_tracks} detail text fields present and valid.")

    # Now check for missing detail MP3s (language bucket + detail/ prefix)
    detail_bucket = _bucket_for(language, "detail")

    # 👇 precompute the storage keys (filename is the track id)
    detail_keys = [_prefixed_key("detail", f"{t.spotify_track_id}.mp3") for t in detail_tracks]

    # existence checks
    detail_tasks = [file_exists_async(detail_bucket, key, client) for key in detail_keys]
    results = await asyncio.gather(*detail_tasks)

    # pair back up so we can log the exact key that’s missing
    missing_pairs = [(t, key) for t, key, exists in zip(detail_tracks, detail_keys, results) if not exists]

    if missing_pairs:
        logger.debug(
            "🛑 %d detail MP3(s) missing:\n%s",
            len(missing_pairs),
            "\n".join(
                f"- title: {t.track_name.ljust(30)} "
                f"artist: {getattr(t, 'artist_display_name', None) or '[unknown]'} "
                f"file: {detail_bucket}/{key}"
                for (t, key) in missing_pairs
            ),
        )
    else:
        logger.debug("✅ All detail MP3s present — no missing files.")

    logger.info(f"🎶 Detail MP3s checked: {len(results)}, missing: {len(missing_pairs)}")

    # preserve previous return shape (list of Track objects)
    return [t for (t, _key) in missing_pairs]

# -------------------------------------------------------------------
# 🎤 Check for missing artist MP3s (concurrent + logs like detail)
# -------------------------------------------------------------------
# 🎤 Check for missing artist MP3s (concurrent + logs like detail)
async def check_artist_mp3s(artists: list, client: httpx.AsyncClient, *, language: str = DEFAULT_TTS_LANGUAGE) -> list:
    """
    Check which artists are missing TTS MP3 files in Supabase.
    Returns a list of Artist objects that are missing files.
    """
    valid_artists = [a for a in artists if a.spotify_artist_id]
    total_artists = len(valid_artists)

    logger.info(f"🎤 Checking {total_artists} artist MP3s...")

    artist_bucket = _bucket_for(language, "artist")
    tasks = [
        file_exists_async(artist_bucket, _prefixed_key("artist", f"{a.spotify_artist_id}.mp3"), client)
        for a in valid_artists
    ]
    results = await asyncio.gather(*tasks)

    missing = [a for a, exists in zip(valid_artists, results) if not exists]

    if missing:
        logger.debug("🛑 Missing artist MP3s:")
        logger.debug("\n" + "\n".join(
            f"- artist: {a.artist_name.ljust(30)}  ID: {a.spotify_artist_id}"
            for a in missing
        ))
    else:
        logger.debug("✅ All artist MP3s present — no missing files.")

    logger.info(f"🎤 Artist MP3s checked: {total_artists}, missing: {len(missing)}")

    return missing

# ------------------------------------------------------------------------------
# 🔍 Master diagnostic function to gather all missing TTS data
# ------------------------------------------------------------------------------
# 🔍 Master diagnostic function to gather all missing TTS data
async def get_missing_tts_info(
    db: Session,
    check_intro_mp3: bool = False,
    check_detail_mp3: bool = False,
    check_artist_mp3: bool = False,
    language: str = DEFAULT_TTS_LANGUAGE,
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
            missing_intro_mp3 = await measure_and_log(
                "Intro MP3s", lambda: check_intro_mp3s(db, client, language=language)
            )

        if check_detail_mp3:
            missing_detail_mp3 = await measure_and_log(
                "Detail MP3s", lambda: check_detail_mp3s(tracks, client, language=language)
            )

        if check_artist_mp3:
            missing_artist_mp3 = await measure_and_log(
                "Artist MP3s", lambda: check_artist_mp3s(artists, client, language=language)
            )

    return {
        "missing_text": {
            "track_detail": missing_detail_text,
            "artist_description": missing_artist_desc,
            "ranking_intro": missing_intro_text,
        },
        "missing_mp3": {
            "track_intro": missing_intro_mp3,
            "track_detail": missing_detail_mp3,
            "artist_mp3": missing_artist_mp3,
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
    headers = ["ID", "Decade", "Genre", "Ranking Count"]
    col_widths = [6, 10, 20, 15]

    # Build the table as a single string block
    lines = []
    separator = "-" * (sum(col_widths) + 9)

    # Header
    header = f"{headers[0]:<{col_widths[0]}} | {headers[1]:<{col_widths[1]}} | {headers[2]:<{col_widths[2]}} | {headers[3]:<{col_widths[3]}}"
    lines.append(separator)
    lines.append(header)
    lines.append(separator)

    # Rows
    for id, decade, genre, count in results:
        line = f"{id:<6} | {decade:<10} | {genre:<20} | {count:<15}"
        lines.append(line)
        summary.append({
            "decade_genre_id": id,
            "decade": decade,
            "genre": genre,
            "ranking_count": count
        })

    lines.append(separator)
    lines.append(f"✅ Total unique decade-genre pairs: {len(summary)}")

    # Log the full block as one message
    logger.info("\n" + "\n".join(lines))

    return summary

# ------------------------------------------------------------------------------
# 🔐 Exported functions
# ------------------------------------------------------------------------------
__all__ = [
    "get_missing_tts_info",
    "get_decade_genre_ranking_summary",
    "normalize_for_filename",  # ✅ Add this line
]

