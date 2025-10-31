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

# ---- FAST LISTING of a folder ----
async def _list_keys(bucket: str, prefix: str, client: httpx.AsyncClient, *, page_size: int = 1000) -> set[str]:
    """
    Return full keys like 'intro/xxx.mp3' for all objects in the given prefix.
    Uses POST /storage/v1/object/list/{bucket} with pagination.
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        logger.error("Supabase not configured; cannot list %s/%s", bucket, prefix)
        return set()

    base = f"{SUPABASE_URL}/storage/v1/object/list/{bucket}"
    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Content-Type": "application/json",
    }

    # Supabase accepts prefix with or without trailing slash; try both
    prefixes_to_try = [prefix.rstrip("/"), prefix.rstrip("/") + "/"]

    all_names: set[str] = set()
    for pref in prefixes_to_try:
        offset = 0
        while True:
            body = {
                "prefix": pref,
                "limit": page_size,
                "offset": offset,
                "sortBy": {"column": "name", "order": "asc"},
            }
            r = await client.post(base, headers=headers, json=body, timeout=HTTP_TIMEOUT)
            if r.status_code != 200:
                # Log once, then bail to next variant
                snippet = (r.text or "")[:200].replace("\n", " ")
                logger.debug("ℹ️ list %s prefix=%s -> %s %s", bucket, pref, r.status_code, snippet)
                break

            items = r.json() or []
            if not items:
                break

            # Items have 'name' relative to the prefix
            for it in items:
                name = it.get("name") or ""
                # exclude "folders" (they come back with no dot or with id==None sometimes)
                if name and "." in name:
                    all_names.add(f"{pref}/{name}" if not pref.endswith("/") else f"{pref}{name}")

            if len(items) < page_size:
                break
            offset += page_size

        if all_names:
            # If one variant worked, we’re done
            break

    logger.debug("📃 Listed %d keys under %s/%s", len(all_names), bucket, prefix)
    return all_names


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
import unicodedata

def normalize_for_filename(text: str) -> str:
    # strip accents, then normalize
    t = unicodedata.normalize("NFKD", text)
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = t.lower().replace(" ", "_").replace("-", "_")
    return re.sub(r"[^a-z0-9_]", "", t)

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
async def check_intro_mp3s(db: Session, client: httpx.AsyncClient, *, language: str = DEFAULT_TTS_LANGUAGE):
    stmt = (
        select(TrackRanking, Decade.decade_name, Genre.genre_name)
        .join(DecadeGenre, TrackRanking.decade_genre_id == DecadeGenre.id)
        .join(Decade, DecadeGenre.decade_id == Decade.id)
        .join(Genre, DecadeGenre.genre_id == Genre.id)
    )
    rows = db.exec(stmt).all()

    intro_bucket = _bucket_for(language, "intro")

    # expected keys
    expected_keys = []
    text_missing_entries = []
    for ranking, decade, genre in rows:
        filename = f"{normalize_for_filename(decade)}_{normalize_for_filename(genre)}_{ranking.ranking:02}.mp3"
        key = _prefixed_key("intro", filename)
        expected_keys.append(key)
        if not ranking.intro or ranking.intro.strip().lower() == "null":
            text_missing_entries.append(f"{ranking.ranking:02} — {decade}, {genre}")

    # existing keys via one list call
    existing = await _list_keys(intro_bucket, "intro", client)
    expected_set = set(expected_keys)
    present = len(existing & expected_set)
    missing_mp3s = sorted(k for k in expected_keys if k not in existing)

    # NEW: orphans (exist in storage but not expected)
    orphans = sorted(existing - expected_set)
    if orphans:
        logger.info("🧹 %d intro orphan file(s) on storage not referenced by DB", len(orphans))
        logger.debug("\n" + "\n".join(f"- {o}" for o in orphans[:100]))

    if missing_mp3s:
        logger.info("🛑 %d intro MP3(s) missing out of %d (present: %d)", len(missing_mp3s), len(expected_keys), present)
        logger.debug("\n" + "\n".join(f"- {name}" for name in missing_mp3s[:100]))
    else:
        logger.info("✅ All intro MP3s present — %d/%d", present, len(expected_keys))

    total_rankings = len(rows)
    if text_missing_entries:
        logger.info("🛑 %d intro text(s) missing/invalid out of %d", len(text_missing_entries), total_rankings)
        logger.debug("\n" + "\n".join(f"- Rank {entry}" for entry in text_missing_entries))
    else:
        logger.info("✅ All %d intro text fields present and valid.", total_rankings)

    stats = {
        "expected": len(expected_keys),
        "present": present,
        "missing": len(missing_mp3s),
        "orphans": len(orphans),
    }
    return missing_mp3s, stats

# ----------------------------------------------------------------------
# 🎶 Check for missing detail MP3s (set-diff + stats)
# ----------------------------------------------------------------------
async def check_detail_mp3s(
    tracks, client: httpx.AsyncClient, *, language: str = DEFAULT_TTS_LANGUAGE
) -> tuple[list[Track], dict[str, int]]:
    lang_code = (language or DEFAULT_TTS_LANGUAGE).strip().lower()
    is_english = lang_code in ("en", "english")

    # ─────────────────────────────────────────────────────────────
    # Filter valid tracks with Spotify IDs
    # ─────────────────────────────────────────────────────────────
    detail_tracks = [t for t in tracks if t.spotify_track_id]
    total_tracks = len(detail_tracks)
    logger.info("🎶 Checking %d detail MP3s for language=%s", total_tracks, lang_code)

    # ─────────────────────────────────────────────────────────────
    # Text presence check — canonical field for EN, locale table for others
    # ─────────────────────────────────────────────────────────────
    if is_english:
        text_missing = [t for t in detail_tracks if not t.detail or not t.detail.strip()]
        if text_missing:
            logger.info(
                "🛑 %d English detail text(s) missing/invalid out of %d",
                len(text_missing),
                total_tracks,
            )
            logger.debug(
                "\n" + "\n".join(f"- {t.track_name} ({t.spotify_track_id})" for t in text_missing[:50])
            )
        else:
            logger.info("✅ All %d English detail text fields present and valid.", total_tracks)
    else:
        # Non-English → check TrackLocale for this language
        from backend.models.dbmodels import TrackLocale
        text_missing = []
        for t in detail_tracks:
            loc_row = None
            if hasattr(t, "locales"):
                loc_row = next(
                    (loc for loc in t.locales if loc.language_code == lang_code and loc.detail_text and loc.detail_text.strip()),
                    None,
                )
            if not loc_row:
                text_missing.append(t)

        if text_missing:
            logger.info(
                "🛑 %d %s detail text(s) missing/invalid out of %d",
                len(text_missing),
                lang_code.upper(),
                total_tracks,
            )
            logger.debug(
                "\n" + "\n".join(f"- {t.track_name} ({t.spotify_track_id})" for t in text_missing[:50])
            )
        else:
            logger.info("✅ All %d %s detail text fields present and valid.", total_tracks, lang_code.upper())

    # ─────────────────────────────────────────────────────────────
    # MP3 presence check (set-diff via Supabase)
    # ─────────────────────────────────────────────────────────────
    detail_bucket = _bucket_for(language, "detail")
    expected_map: dict[str, Track] = {}
    for t in detail_tracks:
        key = _prefixed_key("detail", f"{t.spotify_track_id}.mp3")
        expected_map[key] = t

    existing = await _list_keys(detail_bucket, "detail", client)
    expected_keys = set(expected_map.keys())
    present = len(expected_keys & existing)
    missing_pairs = [(expected_map[k], k) for k in expected_keys if k not in existing]

    # Orphans
    orphans = sorted(existing - expected_keys)
    if orphans:
        logger.info("🧹 %d detail orphan file(s) on storage not referenced by DB", len(orphans))
        logger.debug("\n" + "\n".join(f"- {o}" for o in orphans[:100]))

    if missing_pairs:
        preview_lines = []
        for t, key in missing_pairs[:20]:
            artist = getattr(t, "artist_display_name", None) or "[unknown]"
            preview_lines.append(f"- {t.track_name:<30} | {artist:<25} | {key}")
        suffix = "\n… (truncated)" if len(missing_pairs) > 20 else ""
        logger.debug(
            "🛑 %d detail MP3(s) missing (present: %d/%d):\n%s%s",
            len(missing_pairs),
            present,
            len(expected_keys),
            "\n".join(preview_lines),
            suffix,
        )
    else:
        logger.debug("✅ All detail MP3s present — %d/%d", present, len(expected_keys))

    logger.info(
        "🎶 Detail MP3s expected: %d, present: %d, missing: %d",
        len(expected_keys),
        present,
        len(missing_pairs),
    )

    # Return (missing_tracks, stats)
    stats = {
        "expected": len(expected_keys),
        "present": present,
        "missing": len(missing_pairs),
        "orphans": len(orphans),
    }
    return [t for (t, _key) in missing_pairs], stats

# -------------------------------------------------------------------
# 🎤 Check for missing artist MP3s (set-diff + stats)
# -------------------------------------------------------------------
async def check_artist_mp3s(
    artists: list, client: httpx.AsyncClient, *, language: str = DEFAULT_TTS_LANGUAGE
) -> tuple[list[Artist], dict[str, int]]:
    valid_artists = [a for a in artists if a.spotify_artist_id]
    total_artists = len(valid_artists)
    logger.info("🎤 Checking %d artist MP3s...", total_artists)

    artist_bucket = _bucket_for(language, "artist")
    expected_map: dict[str, Artist] = {}
    for a in valid_artists:
        key = _prefixed_key("artist", f"{a.spotify_artist_id}.mp3")
        expected_map[key] = a

    existing = await _list_keys(artist_bucket, "artist", client)
    expected_keys = set(expected_map.keys())
    present = len(expected_keys & existing)
    missing = [expected_map[k] for k in expected_keys if k not in existing]

    # Orphans: present in storage but not expected
    orphans = sorted(existing - expected_keys)
    if orphans:
        logger.info("🧹 %d artist orphan file(s) on storage not referenced by DB", len(orphans))
        logger.debug("\n" + "\n".join(f"- {o}" for o in orphans[:100]))

    if missing:
        preview = "\n".join(
            f"- artist: {a.artist_name.ljust(30)}  ID: {a.spotify_artist_id}" for a in missing[:50]
        )
        logger.debug(
            "🛑 Missing artist MP3s (%d shown):\n%s%s",
            min(len(missing), 50), preview, "" if len(missing) <= 50 else "\n… (truncated)"
        )
    else:
        logger.debug("✅ All artist MP3s present — %d/%d", present, total_artists)

    logger.info("🎤 Artist MP3s expected: %d, present: %d, missing: %d",
                total_artists, present, len(missing))

    stats = {
        "expected": len(expected_keys),
        "present":  present,
        "missing":  len(missing),
        "orphans":  len(orphans),
    }
    return missing, stats
# -------------------------------------------------------------------
# 🧠 Unified TTS diagnostics across intro, detail, and artist MP3s
# -------------------------------------------------------------------
async def get_missing_tts_info(
    db: Session,
    check_intro_mp3: bool = False,
    check_detail_mp3: bool = False,
    check_artist_mp3: bool = False,
    language: str = DEFAULT_TTS_LANGUAGE,
):
    lang_code = (language or DEFAULT_TTS_LANGUAGE).strip().lower()
    is_english = lang_code in ("en", "english")

    # Load core records
    tracks   = db.exec(select(Track)).all()
    artists  = db.exec(select(Artist)).all()
    rankings = db.exec(select(TrackRanking)).all()

    # ─────────────────────────────────────────────────────────────
    # TEXT PRESENCE CHECKS
    # ─────────────────────────────────────────────────────────────
    if is_english:
        # Canonical EN detail lives in Track.detail
        missing_detail_text = [t for t in tracks if not t.detail or not t.detail.strip()]
    else:
        from backend.models.dbmodels import TrackLocale
        track_ids = [t.id for t in tracks]
        locale_rows = db.exec(
            select(TrackLocale)
            .where(TrackLocale.language_code == lang_code)
            .where(TrackLocale.track_id.in_(track_ids))
        ).all()
        loc_by_id = {loc.track_id: loc for loc in locale_rows}
        missing_detail_text = [
            t for t in tracks
            if t.id not in loc_by_id or not (loc_by_id[t.id].detail_text or "").strip()
        ]

    # Artist description (always English source field)
    missing_artist_desc = [
        a for a in artists if not a.artist_description or not a.artist_description.strip()
    ]

    # Intro text (always English source field)
    missing_intro_text = [
        r for r in rankings if not r.intro or not r.intro.strip()
    ]

    # ─────────────────────────────────────────────────────────────
    # MP3 RESULTS + STATS (defaults)
    # ─────────────────────────────────────────────────────────────
    missing_intro_mp3:  list = []
    missing_detail_mp3: list = []
    missing_artist_mp3: list = []

    intro_stats  = {"expected": 0, "present": 0, "missing": 0, "orphans": 0}
    detail_stats = {"expected": 0, "present": 0, "missing": 0, "orphans": 0}
    artist_stats = {"expected": 0, "present": 0, "missing": 0, "orphans": 0}

    # ─────────────────────────────────────────────────────────────
    # Run async MP3 presence checks
    # ─────────────────────────────────────────────────────────────
    async with httpx.AsyncClient() as client:
        if check_intro_mp3:
            missing_intro_mp3, intro_stats = await measure_and_log(
                "Intro MP3s", lambda: check_intro_mp3s(db, client, language=language)
            )
        if check_detail_mp3:
            missing_detail_mp3, detail_stats = await measure_and_log(
                "Detail MP3s", lambda: check_detail_mp3s(tracks, client, language=language)
            )
        if check_artist_mp3:
            missing_artist_mp3, artist_stats = await measure_and_log(
                "Artist MP3s", lambda: check_artist_mp3s(artists, client, language=language)
            )

    # ─────────────────────────────────────────────────────────────
    # Assemble diagnostics payload
    # ─────────────────────────────────────────────────────────────
    payload = {
        "missing_text": {
            "track_detail":       missing_detail_text,
            "artist_description": missing_artist_desc,
            "ranking_intro":      missing_intro_text,
        },
        "missing_mp3": {
            "track_intro":  missing_intro_mp3,
            "track_detail": missing_detail_mp3,
            "artist_mp3":   missing_artist_mp3,
        },
        "stats": {},
    }

    if check_intro_mp3:
        payload["stats"]["intro"] = intro_stats
    if check_detail_mp3:
        payload["stats"]["detail"] = detail_stats
    if check_artist_mp3:
        payload["stats"]["artist"] = artist_stats

    # Summary log
    logger.info(
        "🧾 TTS Diagnostics summary | lang=%s | intro=%d missing | detail=%d missing | artist=%d missing",
        lang_code,
        len(missing_intro_text),
        len(missing_detail_text),
        len(missing_artist_desc),
    )

    return payload

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

