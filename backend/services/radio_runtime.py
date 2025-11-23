# backend/services/radio_runtime.py
from __future__ import annotations

import asyncio
import logging
import contextlib

from typing import List, Tuple, Optional
from sqlmodel import Session as SQLSession

from backend.database import engine
from backend.services.localization import get_localized_texts
from backend.services.playback_helpers import (
    bucket_for,
    key_for,
    build_intro_filename,
    build_detail_filename,
    build_artist_filename,
    safe_play,
)
from backend.services.spotify.playback import play_spotify_track, stop_spotify_playback
from backend.services.play_policy import compute_play_seconds, sleep_with_skip
from backend.services.radio_render import render_header, box, clean_text, BOX_WIDTH
from backend.config import SPOTIFY_BED_TRACK_ID
from backend.state import skip_event
from backend.routers.playback_control import _flags

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Playback control integration
# ─────────────────────────────────────────────
def _update_flags(
    *,
    phase: str,
    lang: str | None = None,
    mode: str | None = None,
    rank: Optional[int] = None,
    track_name: Optional[str] = None,
    artist_name: Optional[str] = None,
):
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
    """
    Pause/stop/cancel cooperative checkpoint.
    - pause: waits here until resume
    - stop: cancels playback
    - cancel_requested: cancels playback (new sequence started)
    """
    # pause loop
    while getattr(_flags, "is_paused", False):
        await asyncio.sleep(0.25)

    # cancel / stop
    if getattr(_flags, "cancel_requested", False):
        logger.info("🛑 Playback cancelled by new sequence.")
        raise asyncio.CancelledError("Playback cancelled")

    if getattr(_flags, "stopped", False):
        logger.info("🛑 Playback stopped by user.")
        raise asyncio.CancelledError("Playback stopped")


# ─────────────────────────────────────────────
# ✨ Intro-first with bed fade-in/out
# ─────────────────────────────────────────────
async def play_intro_then_bed(
    *,
    intro_label: str,
    bucket: str,
    key: str,
    bed_track_id: str = SPOTIFY_BED_TRACK_ID,
    delay_s: float = 0.25,
    fade_out_s: float = 2.0,
):
    """
    Start intro narration immediately, fade in bed after a short delay,
    and fade bed out after narration finishes OR on cancel/stop.
    """
    intro_task: asyncio.Task[None] | None = None

    try:
        await _respect_user_controls()

        logger.info(
            "🎙️ Starting intro narration (%s), bed fades in after %.2fs",
            key,
            delay_s,
        )
        intro_task = asyncio.create_task(safe_play(intro_label, bucket, key))

        # Fade in bed under narration
        if bed_track_id:
            await asyncio.sleep(delay_s)
            await _respect_user_controls()

            logger.info("🎧 Fading in bed track...")
            play_spotify_track(bed_track_id)

        # Wait for intro to finish, but remain cancel-aware
        while not intro_task.done():
            await _respect_user_controls()
            await asyncio.sleep(0.1)

        # Intro ended normally → fade out bed
        if bed_track_id:
            logger.info("🔉 Fading out bed track...")
            try:
                await stop_spotify_playback(fade_out_seconds=fade_out_s)
            except Exception:
                logger.debug("stop_spotify_playback fade helper unavailable.")

    except asyncio.CancelledError:
        logger.info("⏹ Intro/bed aborted by stop/cancel.")
        # cancel intro mp3 if still running
        if intro_task and not intro_task.done():
            intro_task.cancel()
            with contextlib.suppress(Exception):
                await intro_task

        # fade out bed immediately
        if bed_track_id:
            try:
                await stop_spotify_playback(fade_out_seconds=fade_out_s)
            except Exception:
                pass
        raise

    except Exception as e:
        logger.warning("⚠️ play_intro_then_bed error: %s", e)


# ─────────────────────────────────────────────
# Collection logging
# ─────────────────────────────────────────────
def log_collection_header_and_texts(
    *,
    lang: str,
    collection,
    ctr,
    track,
    artist,
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
def log_header_and_texts(
    *,
    lang: str,
    track,
    artist,
    tr_rows,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Log header + localized texts and return (intro_text, detail_text, artist_text)."""
    header_text = render_header(
        track_name=track.track_name,
        artist_name=getattr(track, "artist_name", None)
        or getattr(artist, "artist_name", "Unknown Artist"),
        track_id=track.spotify_track_id,
        lang=lang,
        tr_rows=tr_rows or [],
    )

    logger.info("\n%s", header_text)

    intro_text_loc, detail_text_loc = None, None
    if tr_rows:
        first_rk = tr_rows[0][0]
        # NOTE: This opens a short-lived session only for localization lookup.
        # With NullPool this is safe and closes immediately.
        with SQLSession(engine) as s_loc:
            intro_text_loc, detail_text_loc = get_localized_texts(
                s_loc, lang, first_rk, track
            )

    logger.info(
        f"[intro:{lang} {'OK' if intro_text_loc else 'FALLBACK'}] "
        f"[detail:{lang} {'OK' if (detail_text_loc and lang == 'pt-BR') else 'FALLBACK/EN'}]"
    )

    if intro_text_loc:
        logger.info(box("INTRO", clean_text(intro_text_loc), width=BOX_WIDTH))

    detail_text = (
        clean_text(detail_text_loc)
        if detail_text_loc
        else clean_text(getattr(track, "detail", None))
    )
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
        jobs.append(
            (
                bucket_for(lang, "intro"),
                key_for("intro", intro_filename),
                decade_name,
                genre_name,
                tr.ranking,
            )
        )
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
# Narration playback
# ─────────────────────────────────────────────
async def play_narrations(
    *,
    play_intro: bool,
    play_detail: bool,
    play_artist: bool,
    intro_jobs,
    detail_bucket,
    detail_key,
    artist_bucket,
    artist_key,
    lang: str = "en",
    mode: str = "decade_genre",
    rank: Optional[int] = None,
    track_name: Optional[str] = None,
    artist_name: Optional[str] = None,
):
    """Play narration audio segments (intro, detail, artist)."""
    try:
        # INTRO(S)
        if play_intro and intro_jobs:
            _update_flags(
                phase="intro",
                lang=lang,
                mode=mode,
                rank=rank,
                track_name=track_name,
                artist_name=artist_name,
            )
            await _respect_user_controls()

            for bkt, key, *_ in intro_jobs:
                await _respect_user_controls()
                logger.info(
                    "🎙️ Playing intro narration with bed fade-in/out: %s", key
                )
                await play_intro_then_bed(
                    intro_label="Intro",
                    bucket=bkt,
                    key=key,
                )

        # DETAIL
        if play_detail and detail_bucket and detail_key:
            _update_flags(
                phase="detail",
                lang=lang,
                mode=mode,
                rank=rank,
                track_name=track_name,
                artist_name=artist_name,
            )
            await _respect_user_controls()

            logger.info("🎙️ Playing detail narration: %s", detail_key)
            await safe_play("Detail", detail_bucket, detail_key)

        # ARTIST DESCRIPTION
        if play_artist and artist_bucket and artist_key:
            _update_flags(
                phase="artist",
                lang=lang,
                mode=mode,
                rank=rank,
                track_name=track_name,
                artist_name=artist_name,
            )
            await _respect_user_controls()

            logger.info("🎙️ Playing artist narration: %s", artist_key)
            await safe_play("Artist", artist_bucket, artist_key)

    except asyncio.CancelledError:
        logger.info("⏹ Narration aborted by stop/cancel.")
        raise
    except Exception as e:
        logger.warning("⚠️ play_narrations error: %s", e)


# ─────────────────────────────────────────────
# Track playback
# ─────────────────────────────────────────────
async def play_track_with_skip(
    *,
    track,
    full_flag: bool,
    lang: str = "en",
    mode: str = "decade_genre",
) -> bool:
    """
    Play Spotify track and wait cooperatively for skip.
    Returns True if skipped/cancelled, False if finished normally.
    """
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
            track.track_name,
            track.spotify_track_id,
            play_secs,
            full_flag,
        )

        play_spotify_track(track.spotify_track_id)

        skipped = await sleep_with_skip(skip_event, play_secs)

        if skipped or getattr(_flags, "cancel_requested", False):
            logger.info("⏭️ track skipped/cancelled → fading out Spotify.")
            try:
                await stop_spotify_playback(fade_out_seconds=1.5)
            except Exception:
                pass
            return True

        logger.info("✅ Track finished normally.")
        return False

    except asyncio.CancelledError:
        logger.info("🛑 Track playback cancelled.")
        try:
            await stop_spotify_playback(fade_out_seconds=1.5)
        except Exception:
            pass
        return True
