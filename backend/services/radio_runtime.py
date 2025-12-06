# backend/services/radio_runtime.py
from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import List, Tuple, Optional
import time

from sqlmodel import Session as SQLSession

from backend.database import engine
from backend.services.localization import get_localized_texts
from backend.services.playback_helpers import (
    bucket_for,
    key_for,
    build_intro_filename,
    build_collection_intro_filename,
    build_detail_filename,
    build_artist_filename,
    safe_play,
)
from backend.services.spotify.playback import (
    play_spotify_track,
    stop_spotify_playback,
    set_device_volume,
)
from backend.services.play_policy import compute_play_seconds, sleep_with_skip
from backend.services.radio_render import render_header, box, clean_text, BOX_WIDTH
from backend.config import SPOTIFY_BED_TRACK_ID
from backend.state import skip_event
from backend.routers.playback_control import _flags

logger = logging.getLogger(__name__)

# Single lock so intros/details/artist narrations never overlap
_narration_lock = asyncio.Lock()


# ─────────────────────────────────────────────
# Safety guard: ensure Spotify volume is sane
# ─────────────────────────────────────────────
async def _ensure_volume_ok() -> None:
    """
    Safety guard so Spotify is never left muted (e.g. mid-fade when user hits NEXT).

    We don't try to be 'smart' here – the goal is simply:
      "If something went weird, make sure we can hear music again."
    """
    try:
        # If you later want this to respect MAIN_VOLUME_PERCENT,
        # you can import it from backend.config.volume and use that instead.
        await set_device_volume(100)
    except Exception:
        # Never let volume repair kill the pipeline
        pass


# ─────────────────────────────────────────────
# Playback control integration helpers
# ─────────────────────────────────────────────
def _update_flags(
    *,
    phase: str,
    lang: str | None = None,
    mode: str | None = None,
    rank: Optional[int] = None,
    track_name: Optional[str] = None,
    artist_name: Optional[str] = None,
    duration_ms: Optional[int] = None,     # ✅ NEWish
) -> None:
    """
    Keep backend.routers.playback_control._flags in sync with the current phase.
    This drives the UI state (car mode, debug panels, etc.).
    """
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
            "durationMs": duration_ms,
        }

        # ✅ Mark the *moment* this phase became active
        _flags.last_action_ts = time.time()

    except Exception:
        logger.debug("⚠️ Failed to update _flags (phase=%s)", phase)


async def _respect_user_controls() -> None:
    """
    Central cooperative checkpoint for:
      • pause / resume
      • stop
      • cancel (new sequence started)
    """
    # Pause: spin here until resume
    while getattr(_flags, "is_paused", False):
        await asyncio.sleep(0.25)

    # Cancel (new sequence)
    if getattr(_flags, "cancel_requested", False):
        logger.info("🛑 Playback cancelled by new sequence.")
        raise asyncio.CancelledError("Playback cancelled")

    # Stop
    if getattr(_flags, "stopped", False):
        logger.info("🛑 Playback stopped by user.")
        raise asyncio.CancelledError("Playback stopped")


# ─────────────────────────────────────────────
# Helpers for clean narration transitions
# ─────────────────────────────────────────────
async def _fade_out_spotify_before_voice(phase: str) -> None:
    """
    If Spotify is currently playing (bed or main track), fade it out
    before starting a *dry* voice-only clip (detail / artist).
    """
    try:
        logger.debug("🔉 Pre-narration fade-out before %s…", phase)
        await stop_spotify_playback(fade_out_seconds=0.8)
    except Exception:
        # Non-fatal
        pass


async def _run_voice_clip_with_skip(kind: str, bucket: str, key: str) -> bool:
    """
    Run safe_play(kind, bucket, key) in a task so we can:
      • honor pause/stop
      • honor NEXT/skip while the MP3 is playing

    Returns:
      True  -> skip detected during this clip
      False -> clip finished normally
    """
    task = asyncio.create_task(safe_play(kind, bucket, key))

    try:
        while not task.done():
            # Global pause / stop / cancel checks
            await _respect_user_controls()

            # 'Skip' button handling (space bar / UI skip)
            if skip_event.is_set():
                skip_event.clear()
                logger.info("⏭️ Skip detected during %s narration; cancelling clip.", kind)
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
                return True

            await asyncio.sleep(0.1)

        # Finished normally
        return False

    except asyncio.CancelledError:
        task.cancel()
        with contextlib.suppress(Exception):
            await task
        raise


# ─────────────────────────────────────────────
# Collection logging helpers
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
    """
    Pretty logging for a collection track:
      • Collection name / slug
      • Rank
      • Track + artist
      • Spotify track id
      • Optional intro + detail + artist description blocks
    """
    header_lines = [
        "┌" + "─" * (BOX_WIDTH - 2),
        "│ TopSpot — Collection",
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
    """
    Build a single intro job for a collection track.

    Returns a list of tuples:
      (bucket, key, collection_slug, collection_slug, rank)
    so it matches the shape expected by play_narrations().
    """
    if lang != "en":
        return []

    bucket = bucket_for(lang, "collections_intro")
    filename = build_collection_intro_filename(collection_slug, rank)
    key = key_for("collections_intro", filename)

    if not (bucket and key):
        return []

    return [(bucket, key, collection_slug, collection_slug, rank)]


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
    """
    Log header + localized texts for decade/genre playback and return:
      (intro_text, detail_text, artist_text)
    """
    header_text = render_header(
        track_name=track.track_name,
        artist_name=getattr(artist, "artist_name", None)
        or getattr(artist, "artist_name", "Unknown Artist"),
        track_id=track.spotify_track_id,
        lang=lang,
        tr_rows=tr_rows or [],
    )
    logger.debug("\n%s", header_text)

    intro_text_loc: str | None = None
    detail_text_loc: str | None = None

    if tr_rows:
        first_rk = tr_rows[0][0]
        with SQLSession(engine) as s_loc:
            intro_text_loc, detail_text_loc = get_localized_texts(
                s_loc, lang, first_rk, track
            )

    logger.debug(
        "[intro:%s %s] [detail:%s %s]",
        lang,
        "OK" if intro_text_loc else "FALLBACK",
        lang,
        "OK" if detail_text_loc else "FALLBACK/EN",
    )

    if intro_text_loc:
        logger.debug(box("INTRO", clean_text(intro_text_loc), width=BOX_WIDTH))

    detail_text = (
        clean_text(detail_text_loc)
        if detail_text_loc
        else clean_text(getattr(track, "detail", None))
    )
    if detail_text:
        logger.debug(box("DETAIL", detail_text, width=BOX_WIDTH))

    artist_text = clean_text(getattr(artist, "artist_description", None))
    if artist_text:
        logger.debug(box("ARTIST", artist_text, width=BOX_WIDTH))

    return intro_text_loc, detail_text, artist_text


# ─────────────────────────────────────────────
# Narration asset builders
# ─────────────────────────────────────────────
def build_intro_jobs(*, lang: str, tr_rows) -> List[Tuple[str, str, str, str, int]]:
    """
    Build intro MP3 jobs for a list of (TrackRanking, decade_name, genre_name).

    Each job is:
      (bucket, key, decade_name, genre_name, rank)
    """
    jobs: List[Tuple[str, str, str, str, int]] = []
    if not tr_rows:
        return jobs

    for tr, decade_name, genre_name in tr_rows:
        intro_filename = build_intro_filename(decade_name, genre_name, tr.ranking)
        bucket = bucket_for(lang, "intro")
        key = key_for("intro", intro_filename)
        if bucket and key:
            jobs.append((bucket, key, decade_name, genre_name, tr.ranking))

    return jobs


def narration_keys_for(*, lang: str, track, artist):
    """
    Build buckets + keys for detail and artist MP3s for a given track/artist.
    """
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
    voice_style: str = "before",  # "before" | "over"
) -> None:
    """
    Play narration in two styles:

    voice_style = "before"
      1) Start bed track for intros
      2) Intro plays over bed
      3) Bed stops
      4) Detail / artist play DRY (no bed)

    voice_style = "over"
      • Assumes the MAIN Spotify track is already playing
      • We 'duck' the volume under all narration
      • No bed track is started/stopped here
    """
    async with _narration_lock:
        try:
            await _respect_user_controls()

            # If skip already pressed, skip entire narration phase
            if skip_event.is_set():
                skip_event.clear()
                logger.info("⏭️ Skip already set — skipping narration phase.")
                return

            # ─────────────────────────────────────────────
            # MODE: VOICE OVER MAIN TRACK
            # ─────────────────────────────────────────────
            if voice_style == "over":
                ducked = False
                try:
                    # Only duck if we actually have something to say
                    if (play_intro and intro_jobs) or (
                        play_detail and detail_bucket and detail_key
                    ) or (play_artist and artist_bucket and artist_key):
                        try:
                            await set_device_volume(40)
                            ducked = True
                            logger.info("🔉 Ducking Spotify volume for voice-over.")
                        except Exception as e:
                            logger.warning(
                                "⚠️ Failed to duck volume for voice-over: %s", e
                            )

                    # 1️⃣ INTRO over track
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
                            if skip_event.is_set():
                                skip_event.clear()
                                logger.info(
                                    "⏭️ Skip hit — skipping remaining intro narration."
                                )
                                break

                            logger.info(
                                "🎙️ Intro narration (over track): %s/%s", bkt, key
                            )
                            await _respect_user_controls()
                            skipped = await _run_voice_clip_with_skip(
                                "Intro", bkt, key
                            )
                            if skipped:
                                logger.info(
                                    "⏭️ Skip during intro; aborting remaining narration."
                                )
                                return

                    # 2️⃣ DETAIL over track
                    if play_detail and detail_bucket and detail_key:
                        if skip_event.is_set():
                            skip_event.clear()
                            logger.info(
                                "⏭️ Skip hit — skipping DETAIL narration (over track)."
                            )
                            return

                        _update_flags(
                            phase="detail",
                            lang=lang,
                            mode=mode,
                            rank=rank,
                            track_name=track_name,
                            artist_name=artist_name,
                        )
                        await _respect_user_controls()

                        logger.info(
                            "🎙️ Detail narration (over track): %s/%s",
                            detail_bucket,
                            detail_key,
                        )
                        skipped = await _run_voice_clip_with_skip(
                            "Detail", detail_bucket, detail_key
                        )
                        if skipped:
                            logger.info(
                                "⏭️ Skip during detail narration; aborting remaining narration."
                            )
                            return

                    # 3️⃣ ARTIST DESCRIPTION over track
                    if play_artist and artist_bucket and artist_key:
                        if skip_event.is_set():
                            skip_event.clear()
                            logger.info(
                                "⏭️ Skip hit — skipping ARTIST narration (over track)."
                            )
                            return

                        _update_flags(
                            phase="artist",
                            lang=lang,
                            mode=mode,
                            rank=rank,
                            track_name=track_name,
                            artist_name=artist_name,
                        )
                        await _respect_user_controls()

                        logger.info(
                            "🎙️ Artist narration (over track): %s/%s",
                            artist_bucket,
                            artist_key,
                        )
                        skipped = await _run_voice_clip_with_skip(
                            "Artist", artist_bucket, artist_key
                        )
                        if skipped:
                            logger.info(
                                "⏭️ Skip during artist narration; aborting remaining narration."
                            )
                            return

                finally:
                    if ducked:
                        try:
                            await set_device_volume(100)
                            logger.info(
                                "🔊 Restored Spotify volume after voice-over narration."
                            )
                        except Exception as e:
                            logger.warning(
                                "⚠️ Failed to restore volume after voice-over: %s", e
                            )

                return  # All done in voice-over mode

            # ─────────────────────────────────────────────
            # MODE: VOICE BEFORE TRACK (CURRENT DEFAULT)
            # ─────────────────────────────────────────────

            # 1️⃣ INTRO — bed plays underneath
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

                # Start bed track immediately
                logger.info("🎧 Starting bed track BEFORE intro narration…")
                play_spotify_track(SPOTIFY_BED_TRACK_ID)
                await asyncio.sleep(0.25)

                # Intro narration over bed
                for bkt, key, *_ in intro_jobs:
                    if skip_event.is_set():
                        skip_event.clear()
                        logger.info("⏭️ Skip hit — skipping remaining intro.")
                        break

                    logger.info("🎙️ Intro narration: %s/%s", bkt, key)
                    await _respect_user_controls()
                    skipped = await _run_voice_clip_with_skip("Intro", bkt, key)
                    if skipped:
                        break

                # Stop bed after intro completes
                logger.info("🔉 Stopping bed track after intro.")
                with contextlib.suppress(Exception):
                    await stop_spotify_playback(fade_out_seconds=1.2)

            # 2️⃣ DETAIL narration (no bed)
            if play_detail and detail_bucket and detail_key:
                if skip_event.is_set():
                    skip_event.clear()
                    logger.info("⏭️ Skip hit — skipping DETAIL narration.")
                    return

                _update_flags(
                    phase="detail",
                    lang=lang,
                    mode=mode,
                    rank=rank,
                    track_name=track_name,
                    artist_name=artist_name,
                )
                await _respect_user_controls()

                logger.info("🎙️ Detail narration: %s/%s", detail_bucket, detail_key)
                await _fade_out_spotify_before_voice("detail")
                skipped = await _run_voice_clip_with_skip(
                    "Detail", detail_bucket, detail_key
                )
                if skipped:
                    return

            # 3️⃣ ARTIST DESCRIPTION narration (no bed)
            if play_artist and artist_bucket and artist_key:
                if skip_event.is_set():
                    skip_event.clear()
                    logger.info("⏭️ Skip hit — skipping ARTIST narration.")
                    return

                _update_flags(
                    phase="artist",
                    lang=lang,
                    mode=mode,
                    rank=rank,
                    track_name=track_name,
                    artist_name=artist_name,
                )
                await _respect_user_controls()

                logger.info("🎙️ Artist narration: %s/%s", artist_bucket, artist_key)
                await _fade_out_spotify_before_voice("artist")
                skipped = await _run_voice_clip_with_skip(
                    "Artist", artist_bucket, artist_key
                )
                if skipped:
                    return

        except asyncio.CancelledError:
            logger.info("⏹ Narration aborted.")
            # Always shut bed down on cancel
            with contextlib.suppress(Exception):
                await stop_spotify_playback(fade_out_seconds=1.0)
            raise
        except Exception as e:
            logger.warning("⚠️ play_narrations error: %s", e)


# ─────────────────────────────────────────────
# Track playback with skip / pause / stop
# (used by decade_genre_player & collections_player)
# ─────────────────────────────────────────────
async def play_track_with_skip(
    track,
    *,
    lang: str = "en",
    mode: str = "decade_genre",
    rank: Optional[int] = None,
    track_name: Optional[str] = None,
    artist_name: Optional[str] = None,
    full_flag: bool = True,
    already_playing: bool = False,
) -> bool:
    """
    Play a Spotify track and wait cooperatively for skip / stop / cancel.

    Returns:
      True  -> track was skipped or cancelled
      False -> track finished normally
    """
    try:
        # Normalize metadata
        rank_val = rank if rank is not None else getattr(track, "ranking", None)
        track_label = track_name or getattr(track, "track_name", None)
        artist_label = artist_name or getattr(track, "artist_name", None)
        spotify_id = getattr(track, "spotify_track_id", None)
        duration_ms = getattr(track, "duration_ms", None)

        if not spotify_id:
            logger.warning("⚠️ No spotify_track_id — skipping track playback.")
            return True

        # Update UI flags
        _update_flags(
            phase="track",
            lang=lang,
            mode=mode,
            rank=rank_val,
            track_name=track_label,
            artist_name=artist_label,
            duration_ms=duration_ms,  # ✅ ADD THIS
        )

        await _respect_user_controls()

        play_secs = compute_play_seconds(track)
        logger.info(
            "🎵 Now playing track: %s (%s) for %ss (full=%s, already_playing=%s)",
            track_label or "Unknown Track",
            spotify_id,
            play_secs,
            full_flag,
            already_playing,
        )

        # If we are *not* in over-track mode, start fresh playback
        if not already_playing:
            # Make sure the device isn't stuck at volume 0
            await _ensure_volume_ok()
            play_spotify_track(spotify_id)

        # Cooperative wait with skip/stop support
        skipped = await sleep_with_skip(skip_event, play_secs)

        if skipped or getattr(_flags, "cancel_requested", False):
            logger.info("⏭️ Track skipped/cancelled → fading out Spotify.")
            with contextlib.suppress(Exception):
                await stop_spotify_playback(fade_out_seconds=1.5)
            return True

        # 🟩 FIX: If track finished AND we were already playing (OVER style),
        # explicitly stop Spotify so that no ghost playback occurs.
        if already_playing:
            logger.info("🔇 Track finished (over-style) — stopping Spotify cleanly.")
            with contextlib.suppress(Exception):
                await stop_spotify_playback(fade_out_seconds=1.0)

        logger.info("✅ Track finished normally.")
        return False


    except asyncio.CancelledError:
        logger.info("🛑 Track playback cancelled.")
        with contextlib.suppress(Exception):
            await stop_spotify_playback(fade_out_seconds=1.5)
        return True
    except Exception as e:
        logger.warning("⚠️ play_track_with_skip error: %s", e)
        with contextlib.suppress(Exception):
            await stop_spotify_playback(fade_out_seconds=1.5)
        return True
