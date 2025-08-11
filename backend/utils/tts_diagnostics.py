# backend/utils/tts_diagnostics.py

import re
import logging
import time
import asyncio
import httpx
from sqlmodel import Session, select, func
from backend.models import (
    Track, Artist, TrackRanking, DecadeGenre, Decade, Genre,
    Specialty, SpecialtyRanking,            # 👈 NEW
)
from backend.utils.filename_builders import build_intro_filename
from backend.config import (
    SUPABASE_URL,
    SUPABASE_SERVICE_ROLE_KEY,
    BUCKET_TRACK_INTRO,
    BUCKET_TRACK_DETAIL,
    BUCKET_SPECIALTY_INTRO,                  # 👈 NEW
)

logger = logging.getLogger("tts_diagnostics")

# ----------------------------------------------------------------------
# 🧽 Normalize names for filenames (used in intro MP3 filenames)
# ----------------------------------------------------------------------
def normalize_for_filename(text: str) -> str:
    return re.sub(r"\W", "", text.lower().replace(" ", "_").replace("-", "_"))

# ----------------------------------------------------------------------
# 🌐 Async check if a file exists in Supabase Storage
# ----------------------------------------------------------------------
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

# ----------------------------------------------------------------------
# 🧩 Helper function to measure time and log a labeled async task
# ----------------------------------------------------------------------
async def measure_and_log(label: str, check_func):
    logger.debug(f"🔍 Starting check: {label}")
    start = time.time()
    result = await check_func()
    duration = time.time() - start
    logger.debug(f"⏱️ {label} check completed in {duration:.2f} seconds")
    return result

# ----------------------------------------------------------------------
# 🎧 Check for missing intro MP3s (TrackRanking)
# ----------------------------------------------------------------------
async def check_intro_mp3s(db: Session, client: httpx.AsyncClient):
    stmt = (
        select(TrackRanking, Decade.decade_name, Genre.genre_name)
        .join(DecadeGenre, TrackRanking.decade_genre_id == DecadeGenre.id)
        .join(Decade, DecadeGenre.decade_id == Decade.id)
        .join(Genre, DecadeGenre.genre_id == Genre.id)
    )
    result = db.exec(stmt).all()

    intro_keys = []
    text_missing_entries = []

    # ...
    for ranking, decade, genre in result:
        # choose the correct field name once: rank or ranking
        rank = getattr(ranking, "rank", None) or getattr(ranking, "ranking", None)
        if rank is None:
            logger.warning(f"⚠️ Missing rank on TrackRanking id={ranking.id}")
            continue

        filename = build_intro_filename(decade, genre, rank)
        intro_keys.append(filename)

        if not ranking.intro or ranking.intro.strip().lower() == "null":
            text_missing_entries.append(f"{ranking.ranking:02} — {decade}, {genre}")

    intro_tasks = [file_exists_async(BUCKET_TRACK_INTRO, key, client) for key in intro_keys]
    results = await asyncio.gather(*intro_tasks)
    missing_mp3s = [key for key, exists in zip(intro_keys, results) if not exists]

    if missing_mp3s:
        logger.info(f"🛑 {len(missing_mp3s)} intro MP3(s) missing out of {len(intro_keys)} total:")
        logger.debug("\n" + "\n".join(f"- {name}" for name in missing_mp3s[:15]))
    else:
        logger.info("✅ All intro MP3s present — no missing files.")

    total_rankings = len(result)
    if text_missing_entries:
        logger.info(f"🛑 {len(text_missing_entries)} intro text(s) missing or invalid out of {total_rankings} total:")
        logger.debug("\n" + "\n".join(f"- Rank {entry}" for entry in text_missing_entries))
    else:
        logger.info(f"✅ All {total_rankings} intro text fields present and valid.")

    return missing_mp3s

# ----------------------------------------------------------------------
# 🌟 NEW: Check for missing specialty intro MP3s (SpecialtyRanking)
#         Same filename pattern as TrackRanking
#         {decade}_{genre}_{rank:02}.mp3
# ----------------------------------------------------------------------

async def check_specialty_intro_mp3s(db: Session, client: httpx.AsyncClient):
    """
    Check Specialty intro MP3s in BUCKET_SPECIALTY_INTRO using the SAME pattern as TrackRanking:
      {decade}_{genre}_{rank:02}.mp3
    We attempt to derive decade/genre via joins; otherwise we fall back to placeholders.
    """

    # Try several join paths; outer joins keep it tolerant if columns don’t exist.
    from sqlmodel import select

    stmt = (
        select(SpecialtyRanking, Specialty, Decade, Genre)  # <= 4 entities
        .join(Specialty, Specialty.id == SpecialtyRanking.specialty_id)
        .join(DecadeGenre, DecadeGenre.id == SpecialtyRanking.decade_genre_id, isouter=True)
        .join(Decade, Decade.id == DecadeGenre.decade_id, isouter=True)
        .join(Genre, Genre.id == DecadeGenre.genre_id, isouter=True)
    )

    rows = db.exec(stmt).all()

    intro_keys: list[str] = []
    text_missing_entries: list[str] = []

    for sr, sp, dec, gen in rows:
        rank = getattr(sr, "rank", None) or getattr(sr, "ranking", None)
        if rank is None:
            logger.warning(f"⚠️ Missing rank for specialty_id={sp.id}, track_id={sr.track_id}")
            continue

        decade_name = getattr(dec, "decade_name", None) or getattr(sr, "decade", None) or getattr(sr, "category",
                                                                                                  None) or "unknown"
        genre_name = getattr(gen, "genre_name", None) or getattr(sr, "genre", None) or "unknown"

        filename = build_intro_filename(decade_name, genre_name, rank)  # shared builder
        intro_keys.append(filename)

        intro_text = (getattr(sr, "intro", "") or "").strip().lower()
        if not intro_text or intro_text == "null":
            text_missing_entries.append(f"{int(rank):02} — {decade_name}, {genre_name}")

    tasks = [file_exists_async(BUCKET_SPECIALTY_INTRO, key, client) for key in intro_keys]
    results = await asyncio.gather(*tasks)
    missing_mp3s = [key for key, exists in zip(intro_keys, results) if not exists]

    total = len(rows)
    if missing_mp3s:
        logger.info(f"🛑 {len(missing_mp3s)} specialty intro MP3(s) missing out of {total} total.")
        logger.debug("\n" + "\n".join(f"- {name}" for name in missing_mp3s[:15]))
    else:
        logger.info("✅ All specialty intro MP3s present — no missing files.")

    if text_missing_entries:
        logger.info(f"🛑 {len(text_missing_entries)} specialty intro text(s) missing or invalid out of {total} total.")
        logger.debug("\n" + "\n".join(f"- Rank {entry}" for entry in text_missing_entries))
    else:
        logger.info(f"✅ All {total} specialty intro text fields present and valid.")

    return missing_mp3s
# ----------------------------------------------------------------------
# 🎶 Check for missing detail MP3s
# ----------------------------------------------------------------------
async def check_detail_mp3s(tracks, client: httpx.AsyncClient):
    detail_tracks = [t for t in tracks if t.spotify_track_id]

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

    detail_tasks = [
        file_exists_async(BUCKET_TRACK_DETAIL, f"{t.spotify_track_id}.mp3", client)
        for t in detail_tracks
    ]
    results = await asyncio.gather(*detail_tasks)

    missing = [t for t, exists in zip(detail_tracks, results) if not exists]
    if missing:
        logger.debug(
            "🛑 {n} detail MP3(s) missing:\n".format(n=len(missing)) +
            "\n".join(
                f"- title: {t.track_name.ljust(30)} artist: {t.artist_display_name or '[unknown]'}"
                for t in missing
            )
        )
    else:
        logger.debug("✅ All detail MP3s present — no missing files.")

    logger.info(f"🎶 Detail MP3s checked: {len(results)}, missing: {len(missing)}")

    return missing

# -------------------------------------------------------------------
# 🎤 Check for missing artist MP3s
# -------------------------------------------------------------------
async def check_artist_mp3s(artists: list, client: httpx.AsyncClient) -> list:
    from backend.config import SUPABASE_BUCKET_ARTIST_MP3

    valid_artists = [a for a in artists if a.spotify_artist_id]
    total_artists = len(valid_artists)

    logger.info(f"🎤 Checking {total_artists} artist MP3s...")

    tasks = [
        file_exists_async(SUPABASE_BUCKET_ARTIST_MP3, f"{a.spotify_artist_id}.mp3", client)
        for a in valid_artists
    ]
    results = await asyncio.gather(*tasks)

    missing = [a for a, exists in zip(valid_artists, results) if not exists]

    if missing:
        logger.debug("🛑 Missing artist MP3s:\n" + "\n".join(
            f"- artist: {a.artist_name.ljust(30)}  ID: {a.spotify_artist_id}"
            for a in missing
        ))
    else:
        logger.debug("✅ All artist MP3s present — no missing files.")

    logger.info(f"🎤 Artist MP3s checked: {total_artists}, missing: {len(missing)}")

    return missing

# ----------------------------------------------------------------------
# 🔍 Master diagnostic function to gather all missing TTS data
# ----------------------------------------------------------------------
async def get_missing_tts_info(
    db: Session,
    check_intro_mp3: bool = False,
    check_detail_mp3: bool = False,
    check_artist_mp3: bool = False,
    check_specialty_intro_mp3: bool = False,   # 👈 NEW
):
    # Load records
    tracks = db.exec(select(Track)).all()
    artists = db.exec(select(Artist)).all()
    rankings = db.exec(select(TrackRanking)).all()

    # 🔤 Missing TEXT (core)
    missing_detail_text = [t for t in tracks if not t.detail or not t.detail.strip()]
    missing_artist_desc = [a for a in artists if not a.artist_description or not a.artist_description.strip()]
    missing_intro_text = [r for r in rankings if not r.intro or not r.intro.strip()]

    # 🔈 Missing MP3s (optional)
    missing_intro_mp3 = []
    missing_detail_mp3 = []
    missing_artist_mp3 = []
    missing_specialty_intro_mp3 = []  # 👈 NEW

    async with httpx.AsyncClient() as client:
        if check_intro_mp3:
            missing_intro_mp3 = await measure_and_log("Intro MP3s", lambda: check_intro_mp3s(db, client))
        if check_detail_mp3:
            missing_detail_mp3 = await measure_and_log("Detail MP3s", lambda: check_detail_mp3s(tracks, client))
        if check_artist_mp3:
            missing_artist_mp3 = await measure_and_log("Artist MP3s", lambda: check_artist_mp3s(artists, client))
        if check_specialty_intro_mp3:
            missing_specialty_intro_mp3 = await measure_and_log(
                "Specialty Intro MP3s", lambda: check_specialty_intro_mp3s(db, client)
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
            "specialty_intro": missing_specialty_intro_mp3,  # 👈 NEW
        }
    }

# ----------------------------------------------------------------------
# 📊 Summary of decade-genre combinations with ranking counts
# ----------------------------------------------------------------------
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

    lines = []
    separator = "-" * (sum(col_widths) + 9)

    header = f"{headers[0]:<{col_widths[0]}} | {headers[1]:<{col_widths[1]}} | {headers[2]:<{col_widths[2]}} | {headers[3]:<{col_widths[3]}}"
    lines.append(separator)
    lines.append(header)
    lines.append(separator)

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
    logger.info("\n" + "\n".join(lines))

    return summary

__all__ = [
    "get_missing_tts_info",
    "get_decade_genre_ranking_summary",
    "normalize_for_filename",
]
