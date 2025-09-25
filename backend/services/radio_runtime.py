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

logger = logging.getLogger(__name__)

# ---------- Logging / texts ----------
def log_header_and_texts(*, lang: str, track, artist, tr_rows) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Log the header + localized text blocks. Returns (intro_text, detail_text, artist_text)."""
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

# ---------- Narration assets ----------
def build_intro_jobs(*, lang: str, tr_rows) -> List[Tuple[str, str, str, str, int]]:
    """
    Return a list of (bucket, key, decade, genre, rank) for intros.
    """
    jobs: List[Tuple[str, str, str, str, int]] = []
    if not tr_rows:
        return jobs
    for tr, decade_name, genre_name in tr_rows:
        intro_filename = build_intro_filename(decade_name, genre_name, tr.ranking)
        jobs.append((bucket_for(lang, "intro"), key_for("intro", intro_filename), decade_name, genre_name, tr.ranking))
    return jobs

def narration_keys_for(*, lang: str, track, artist):
    detail_filename = build_detail_filename(track.spotify_track_id)
    artist_filename = build_artist_filename(artist.spotify_artist_id)

    detail_key   = key_for("detail", detail_filename) if detail_filename else None
    artist_key   = key_for("artist", artist_filename) if artist_filename else None

    detail_bucket = bucket_for(lang, "detail") if detail_key else None
    artist_bucket = bucket_for(lang, "artist") if artist_key else None
    return detail_bucket, detail_key, artist_bucket, artist_key

# ---------- Playback pieces ----------
async def maybe_play_bed():
    if not SPOTIFY_BED_TRACK_ID:
        return
    try:
        play_spotify_track(SPOTIFY_BED_TRACK_ID)
        await asyncio.sleep(0.5)
    except Exception as e:
        logger.warning("Bed track failed: %s", e)

async def play_narrations(*, play_intro: bool, play_detail: bool, play_artist: bool,
                          intro_jobs, detail_bucket, detail_key, artist_bucket, artist_key):
    if play_intro and intro_jobs:
        for bkt, key, _, _, _ in intro_jobs:
            await safe_play("Intro", bkt, key)
    if play_detail and detail_bucket and detail_key:
        await safe_play("Detail", detail_bucket, detail_key)
    if play_artist and artist_bucket and artist_key:
        await safe_play("Artist", artist_bucket, artist_key)

async def play_track_with_skip(*, track, full_flag: bool) -> bool:
    """
    Start Spotify track and cooperatively wait. Returns True if skip triggered.
    """
    play_secs = compute_play_seconds(track)
    logger.info("🎵 Now playing track: %s (%s) for %ss (full=%s)",
                track.track_name, track.spotify_track_id, play_secs, full_flag)
    play_spotify_track(track.spotify_track_id)
    # IMPORTANT: pass the global skip_event to the helper
    return await sleep_with_skip(skip_event, play_secs)
