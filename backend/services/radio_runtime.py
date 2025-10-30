# backend/services/radio_runtime.py
from __future__ import annotations
import asyncio
import logging
from typing import List, Tuple, Optional
from sqlmodel import Session as SQLSession

from backend.database import engine
from backend.services.localization import get_localized_texts
from backend.services.playback_helpers import (
    bucket_for, key_for,
    build_intro_filename, build_detail_filename, build_artist_filename,
    safe_play,
)
from backend.services.spotify.playback import play_spotify_track
from backend.services.play_policy import compute_play_seconds, sleep_with_skip
from backend.services.radio_render import render_header, box, clean_text, BOX_WIDTH
from backend.config import SPOTIFY_BED_TRACK_ID
from backend.state import skip_event
from backend.routers.playback_control import _flags

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Playback control integration
# ─────────────────────────────────────────────
def _update_flags(*, phase: str, lang: str | None = None,
                  mode: str | None = None, rank: Optional[int] = None,
                  track_name: Optional[str] = None,
                  artist_name: Optional[str] = None):
    """Keep playback_control._flags in sync with the current playback phase."""
    try:
        _flags.is_playing = True
        _flags.is_paused = False
        _flags.stopped = False
        if lang:
            _flags.language = lang
        if mode:
            _flags.mode = mode
        if rank is not None:
            _flags.current_rank = rank
        _flags.context = {
            "phase": phase,
            "rank": rank,
            "track_name": track_name,
            "artist_name": artist_name,
        }
    except Exception:
        logger.debug("⚠️ Failed to update _flags (phase=%s)", phase)


async def _respect_user_controls():
    """Pause/stop cooperative checkpoint."""
    while getattr(_flags, "is_paused", False):
        await asyncio.sleep(0.25)
    if getattr(_flags, "stopped", False):
        logger.info("🛑 Playback stopped by user.")
        raise asyncio.CancelledError("Playback stopped")


# ─────────────────────────────────────────────
# Collection logging
# ─────────────────────────────────────────────
def log_collection_header_and_texts(
    *, lang: str, collection, ctr, track, artist,
    intro: str | None = None,
    detail_text: str | None = None,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Log collection header and text blocks."""
    header_lines = [
        "┌" + "─" * (BOX_WIDTH - 2),
        f"│ TopSpot — Collection",
        f"│  Name : {getattr(collection, 'name', collection.slug)}",
        f"│  Slug : {collection.slug}",
        f"│  Rank : #{ctr.ranking:02d}",
        f"│  Track: {track.track_name} — {getattr(artist, 'artist_name', '')}",
        f"│  Spotify Track ID: {getattr(track, 'spotify_track_id', '') or '—'}",
        "└" + "─" * (BOX_WIDTH - 2),
    ]
    logger.info("\n%s", "\n".join(header_lines))

    intro_text = clean_text(intro or getattr(ctr, "intro", None))
    if intro_text:
        logger.info(box("INTRO", intro_text, width=BOX_WIDTH))

    detail_text = clean_text(detail_text or getattr(track, "detail", None))
    if detail_text:
        logger.info(box("DETAIL", detail_text, width=BOX_WIDTH))

    artist_text = clean_text(getattr(artist, "artist_description", None))
    if artist_text:
        logger.info(box("ARTIST", artist_text, width=BOX_WIDTH))

    return intro_text, detail_text, artist_text


def collection_intro_jobs(*, lang: str, collection_slug: str, rank: int):
    """Return intro narration job for collections."""
    if lang != "en":
        return []
    bkt = bucket_for("en", "intro")
    key = f"collections-intro/{collection_slug}_{rank:02d}.mp3"
    return [(bkt, key, collection_slug, collection_slug, rank)]


# ─────────────────────────────────────────────
# Decade/Genre header logging
# ─────────────────────────────────────────────
def log_header_and_texts(*, lang: str, track, artist, tr_rows) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Log header + localized texts and return (intro_text, detail_text, artist_text)."""
    header_text = render_header(
        track_name=track.track_name,
        artist_name=artist.artist_name,
        track_id=track.spotify_track_id,
        lang=lang,
        tr_rows=tr_rows or [],
    )
    logger.info("\n%s", header_text)

    intro_text_loc, detail_text_loc = None, None
    if tr_rows:
        first_rk = tr_rows[0][0]
        with SQLSession(engine) as s_loc:
            intro_text_loc, detail_text_loc = get_localized_texts(s_loc, lang, first_rk, track)

    logger.info(
        f"[intro:{lang} {'OK' if intro_text_loc else 'FALLBACK'}] "
        f"[detail:{lang} {'OK' if (detail_text_loc and lang == 'pt-BR') else 'FALLBACK/EN'}]"
    )

    if intro_text_loc:
        logger.info(box("INTRO", clean_text(intro_text_loc), width=BOX_WIDTH))

    detail_text = clean_text(detail_text_loc) if detail_text_loc else clean_text(getattr(track, "detail", None))
    if detail_text:
        logger.info(box("DETAIL", detail_text, width=BOX_WIDTH))

    artist_text = clean_text(getattr(artist, "artist_description", None))
    if artist_text:
        logger.info(box("ARTIST", artist_text, width=BOX_WIDTH))

    return intro_text_loc, detail_text, artist_text


# ─────────────────────────────────────────────
# Narration asset builders
# ─────────────────────────────────────────────
def build_intro_jobs(*, lang: str, tr_rows) -> List[Tuple[str, str, str, str, int]]:
    """Return (bucket, key, decade, genre, rank) for intros."""
    jobs: List[Tuple[str, str, str, str, int]] = []
    if not tr_rows:
        return jobs
    for tr, decade_name, genre_name in tr_rows:
        intro_filename = build_intro_filename(decade_name, genre_name, tr.ranking)
        jobs.append((bucket_for(lang, "intro"), key_for("intro", intro_filename), decade_name, genre_name, tr.ranking))
    return jobs


def narration_keys_for(*, lang: str, track, artist):
    """Return buckets + keys for detail and artist narrations."""
    detail_filename = build_detail_filename(track.spotify_track_id)
    artist_filename = build_artist_filename(artist.spotify_artist_id)

    detail_key = key_for("detail", detail_filename) if detail_filename else None
    artist_key = key_for("artist", artist_filename) if artist_filename else None

    detail_bucket = bucket_for(lang, "detail") if detail_key else None
    artist_bucket = bucket_for(lang, "artist") if artist_key else None

    return detail_bucket, detail_key, artist_bucket, artist_key


# ─────────────────────────────────────────────
# Playback helpers
# ─────────────────────────────────────────────
async def maybe_play_bed():
    """Play soft bed track before narration."""
    if not SPOTIFY_BED_TRACK_ID:
        return
    try:
        logger.info("🎧 Starting bed track (5s ambient intro)")
        play_spotify_track(SPOTIFY_BED_TRACK_ID)
        await asyncio.sleep(5)
        logger.info("🎧 Bed intro finished; continuing to sequence playback.")
    except Exception as e:
        logger.warning("Bed track failed: %s", e)


async def play_narrations(*, play_intro: bool, play_detail: bool, play_artist: bool,
                          intro_jobs, detail_bucket, detail_key, artist_bucket, artist_key,
                          lang: str = "en", mode: str = "decade_genre",
                          rank: Optional[int] = None, track_name: Optional[str] = None,
                          artist_name: Optional[str] = None):
    """Play narration audio segments (intro, detail, artist)."""
    try:
        if play_intro and intro_jobs:
            _update_flags(phase="intro", lang=lang, mode=mode, rank=rank,
                          track_name=track_name, artist_name=artist_name)
            await _respect_user_controls()
            for bkt, key, *_ in intro_jobs:
                logger.info(f"🎙️ Playing intro narration: {key}")
                await safe_play("Intro", bkt, key)

        if play_detail and detail_bucket and detail_key:
            _update_flags(phase="detail", lang=lang, mode=mode, rank=rank,
                          track_name=track_name, artist_name=artist_name)
            await _respect_user_controls()
            logger.info(f"🎙️ Playing detail narration: {detail_key}")
            await safe_play("Detail", detail_bucket, detail_key)

        if play_artist and artist_bucket and artist_key:
            _update_flags(phase="artist", lang=lang, mode=mode, rank=rank,
                          track_name=track_name, artist_name=artist_name)
            await _respect_user_controls()
            logger.info(f"🎙️ Playing artist narration: {artist_key}")
            await safe_play("Artist", artist_bucket, artist_key)

    except asyncio.CancelledError:
        logger.info("⏹ Narration aborted by stop command.")
    except Exception as e:
        logger.warning("⚠️ play_narrations error: %s", e)


async def play_track_with_skip(*, track, full_flag: bool, lang: str = "en", mode: str = "decade_genre") -> bool:
    """Play Spotify track and wait cooperatively for skip."""
    try:
        _update_flags(
            phase="track",
            lang=lang,
            mode=mode,
            rank=getattr(track, "ranking", None),
            track_name=getattr(track, "track_name", None),
            artist_name=getattr(track, "artist_name", None),
        )
        await _respect_user_controls()

        play_secs = compute_play_seconds(track)
        logger.info(
            "🎵 Now playing track: %s (%s) for %ss (full=%s)",
            track.track_name, track.spotify_track_id, play_secs, full_flag,
        )
        play_spotify_track(track.spotify_track_id)
        return await sleep_with_skip(skip_event, play_secs)

    except asyncio.CancelledError:
        logger.info("🛑 Track playback cancelled.")
        return True
