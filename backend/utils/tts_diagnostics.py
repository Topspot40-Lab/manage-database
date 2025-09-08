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

def _chunked(seq, size: int):
    for i in range(0, len(seq), size):
        yield seq[i:i+size]


# ------------------------------------------------------------------------------
# 🧽 Normalize names for filenames (used in intro MP3 filenames)
# ------------------------------------------------------------------------------
def normalize_for_filename(text: str) -> str:
    return re.sub(r"\W", "", text.lower().replace(" ", "_").replace("-", "_"))

# ------------------------------------------------------------------------------
# 🌐 Async check if a file exists in Supabase Storage
# ------------------------------------------------------------------------------
MAX_IN_FLIGHT = 24
HTTP_TIMEOUT  = 12.0
RETRY_ON      = {429, 500, 502, 503, 504}
_sem = asyncio.Semaphore(MAX_IN_FLIGHT)

async def _sb_get(client: httpx.AsyncClient, url: str, headers: dict):
    async with _sem:
        return await client.get(url, headers=headers, timeout=HTTP_TIMEOUT)

async def _sb_post(client: httpx.AsyncClient, url: str, headers: dict, json: dict | None = None):
    async with _sem:
        return await client.post(url, headers=headers, json=json, timeout=HTTP_TIMEOUT)

async def file_exists_async(bucket: str, path: str, client: httpx.AsyncClient) -> bool:
    """
    Try 1: GET /storage/v1/object/info/{bucket}/{path}
    Try 2: POST /storage/v1/object/sign/{bucket}/{path} then HEAD the signed URL
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        logger.error("Supabase not configured; cannot check %s/%s", bucket, path)
        return False

    # ----------- Try 1: object/info -----------
    info_url = f"{SUPABASE_URL}/storage/v1/object/info/{bucket}/{path}"
    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
    }

    try:
        logger.debug("🌐 [info] %s", info_url)
        r = await _sb_get(client, info_url, headers)
        if r.status_code == 200:
            return True
        if r.status_code in RETRY_ON:
            await asyncio.sleep(0.5)
            r = await _sb_get(client, info_url, headers)
            if r.status_code == 200:
                return True

        # Not found vs other errors
        if r.status_code == 404:
            logger.debug("❌ [info] 404 not found for %s/%s", bucket, path)
        else:
            snippet = (r.text or "")[:200].replace("\n", " ")
            logger.debug("ℹ️ [info] %s -> %s %s", info_url, r.status_code, snippet)
    except httpx.HTTPError as e:
        logger.warning("⚠️ [info] %s -> %s", info_url, repr(e))
    except Exception as e:
        logger.warning("⚠️ [info] unexpected error for %s: %s", info_url, e)

    # ----------- Try 2: sign + HEAD -----------
    sign_url = f"{SUPABASE_URL}/storage/v1/object/sign/{bucket}/{path}"
    try:
        logger.debug("🌐 [sign] %s", sign_url)
        # expiresIn is seconds
        sr = await _sb_post(client, sign_url, headers, json={"expiresIn": 60})
        if sr.status_code != 200:
            snippet = (sr.text or "")[:200].replace("\n", " ")
            logger.debug("ℹ️ [sign] %s -> %s %s", sign_url, sr.status_code, snippet)
            return False

        data = sr.json()
        signed_url = data.get("signedURL") or data.get("signedUrl") or data.get("signed_url")
        if not signed_url:
            logger.debug("ℹ️ [sign] no signedURL field present in response")
            return False

        # Signed URL might be relative; prepend origin if needed
        if signed_url.startswith("/"):
            signed_url = f"{SUPABASE_URL}{signed_url}"

        # HEAD the signed URL (public fetch)
        logger.debug("🌐 [head] %s", signed_url)
        async with _sem:
            hr = await client.head(signed_url, timeout=HTTP_TIMEOUT, follow_redirects=True)
        if hr.status_code == 200:
            return True
        # Sometimes HEAD is blocked; try a lightweight GET with range header
        if hr.status_code in RETRY_ON or hr.status_code == 405:
            async with _sem:
                gr = await client.get(signed_url, headers={"Range": "bytes=0-0"}, timeout=HTTP_TIMEOUT)
            if gr.status_code in (200, 206):
                return True
            logger.debug("ℹ️ [head->get] %s -> %s", signed_url, gr.status_code)
        else:
            logger.debug("ℹ️ [head] %s -> %s", signed_url, hr.status_code)
    except httpx.HTTPError as e:
        logger.warning("⚠️ [sign/head] %s -> %s", sign_url, repr(e))
    except Exception as e:
        logger.warning("⚠️ [sign/head] unexpected error for %s: %s", sign_url, e)

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
        logger.debug("🔎 Intro probe → bucket=%s key=%s", intro_bucket, intro_keys[-1])

        # Check for missing/empty/null text
        if not ranking.intro or ranking.intro.strip().lower() == "null":
            text_missing_entries.append(f"{ranking.ranking:02} — {decade}, {genre}")

    # Check missing MP3s (language-scoped bucket + intro/ prefix)
    results = []
    for batch in _chunked(intro_keys, 32):
        # optional: log first few to verify shape
        for k in batch[:3]:
            logger.debug("🔎 Intro probe → bucket=%s key=%s", intro_bucket, k)
        tasks = [file_exists_async(intro_bucket, key, client) for key in batch]
        results.extend(await asyncio.gather(*tasks))

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

    # existence checks (batched)
    results = []
    for batch in _chunked(detail_keys, 32):
        for k in batch[:3]:
            logger.debug("🔎 Detail probe → bucket=%s key=%s", detail_bucket, k)
        tasks = [file_exists_async(detail_bucket, key, client) for key in batch]
        results.extend(await asyncio.gather(*tasks))

    # pair back up so we can log the exact key that’s missing
    missing_pairs = [(t, key) for t, key, exists in zip(detail_tracks, detail_keys, results) if not exists]

    if missing_pairs:
        # only print the first N for readability
        limit = 15
        mp = list(missing_pairs)  # ensure sliceable/countable
        total = len(mp)

        lines = []
        for t, key in mp[:limit]:
            title = (t.track_name or "").ljust(30)
            artist = getattr(t, "artist_display_name", None) or "[unknown]"
            lines.append(f"- title: {title} artist: {artist} file: {detail_bucket}/{key}")

        suffix = "\n… (truncated)" if total > limit else ""
        logger.debug(
            "🛑 %d detail MP3(s) missing (showing first %d):\n%s%s",
            total, min(total, limit), "\n".join(lines), suffix
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

async def check_artist_mp3s(
    artists: list, client: httpx.AsyncClient, *, language: str = DEFAULT_TTS_LANGUAGE
) -> list:
    """
    Check which artists are missing TTS MP3 files in Supabase.
    Returns a list of Artist objects that are missing files.
    """
    valid_artists = [a for a in artists if a.spotify_artist_id]
    total_artists = len(valid_artists)

    logger.info(f"🎤 Checking {total_artists} artist MP3s...")

    artist_bucket = _bucket_for(language, "artist")
    artist_keys = [_prefixed_key("artist", f"{a.spotify_artist_id}.mp3") for a in valid_artists]

    results: list[bool] = []

    # 🔄 batch requests to avoid timeouts / rate limits
    for batch in _chunked(list(zip(valid_artists, artist_keys)), 32):
        # optional: show first few keys for sanity
        for a, k in batch[:3]:
            logger.debug("🔎 Artist probe → bucket=%s key=%s (artist=%s)", artist_bucket, k, a.artist_name)
        tasks = [file_exists_async(artist_bucket, k, client) for _, k in batch]
        batch_results = await asyncio.gather(*tasks)
        results.extend(batch_results)

    missing = [a for a, exists in zip(valid_artists, results) if not exists]

    if missing:
        logger.debug("🛑 Missing artist MP3s:")
        logger.debug(
            "\n" + "\n".join(f"- artist: {a.artist_name.ljust(30)}  ID: {a.spotify_artist_id}" for a in missing)
        )
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

