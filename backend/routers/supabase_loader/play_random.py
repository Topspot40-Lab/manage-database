# backend/routers/supabase_loader/play_random.py
from __future__ import annotations

import asyncio
import logging
from typing import Literal

from fastapi import APIRouter, Query
from sqlmodel import Session as SQLSession
from sqlalchemy.exc import OperationalError, InterfaceError

from backend.database import engine
from backend.state import skip_event
from backend.utils.naming import normalize_language_code_canon

from backend.services.radio_pick import fetch_random_pick
from backend.config.volume import PLAY_FULL_TRACK

# Unified runtime pipeline (safe narrations + track playback)
from backend.services.radio_runtime import (
    log_header_and_texts,
    build_intro_jobs,
    narration_keys_for,
    play_narrations,
    play_track_with_skip,
)

# Cache viewer
from backend.services.supabase_loader_service import current_decade_genre_tracks


logger = logging.getLogger(__name__)
router = APIRouter(tags=["Supabase: Play Random"])


# ─────────────────────────────────────────────
# PLAY RANDOM TRACK(S)
# ─────────────────────────────────────────────
@router.get("/play-random-track-from-db")
async def play_random_track_from_db(
    play_intro: bool = Query(True, description="Play intro MP3(s) if available"),
    play_detail: bool = Query(True, description="Play detail MP3 if available"),
    play_artist_description: bool = Query(True, description="Play artist description MP3 if available"),
    play_track: bool = Query(True, description="Play the Spotify track"),
    num_tracks: int = Query(1, description="How many random tracks to play (-1 = keep playing forever)"),
    tts_language: Literal["en", "es", "ptbr", "pt-BR"] = Query("en"),
):
    """
    Pick random tracks from DB and play them sequentially with narration.
    Uses the unified narration pipeline (bed under intro, detail+artist normal).
    """
    lang = normalize_language_code_canon(tts_language)
    played, count = [], 0

    async def _play_one() -> dict | None:
        # --- Fetch random pick from DB with failover ---
        with SQLSession(engine) as s:
            try:
                pick = fetch_random_pick(s)
            except (OperationalError, InterfaceError) as e:
                logger.warning("DB connection dropped; retrying once: %s", e)
                try:
                    s.rollback()
                except Exception:
                    pass
                pick = fetch_random_pick(s)

        if not pick:
            logger.warning("No playable tracks found with spotify_track_id.")
            return None

        track, artist, tr_rows = pick.track, pick.artist, pick.rankings

        # Log header + localized text (if any)
        log_header_and_texts(lang=lang, track=track, artist=artist, tr_rows=tr_rows)

        # Narration asset keys
        intro_jobs = build_intro_jobs(lang=lang, tr_rows=tr_rows) if play_intro else []
        detail_bucket, detail_key, artist_bucket, artist_key = narration_keys_for(
            lang=lang, track=track, artist=artist
        )

        # ════════════════════════════════════════════
        #     UNIFIED NARRATION (INTRO/DETAIL/ARTIST)
        # ════════════════════════════════════════════
        await play_narrations(
            play_intro=play_intro,
            play_detail=play_detail,
            play_artist=play_artist_description,
            intro_jobs=intro_jobs,
            detail_bucket=detail_bucket,
            detail_key=detail_key,
            artist_bucket=artist_bucket,
            artist_key=artist_key,
            lang=lang,
            mode="random",
            rank=tr_rows[0][0].ranking if tr_rows else None,
            track_name=track.track_name,
            artist_name=artist.artist_name,
        )

        # ════════════════════════════════════════════
        #     TRACK PLAYBACK (with skip support)
        # ════════════════════════════════════════════
        skipped_mid = False
        if play_track and track.spotify_track_id:
            try:
                skipped_mid = await play_track_with_skip(
                    track=track,
                    lang=lang,
                    mode="random",
                    rank=tr_rows[0][0].ranking if tr_rows else None,
                    track_name=track.track_name,
                    artist_name=artist.artist_name,
                    full_flag=PLAY_FULL_TRACK,
                )
            except Exception as e:
                logger.exception("Failed to play track: %s", e)

        return {
            "track": {"id": track.id, "name": track.track_name, "spotify_track_id": track.spotify_track_id},
            "artist": {"id": artist.id, "name": artist.artist_name, "spotify_artist_id": artist.spotify_artist_id},
            "skipped": skipped_mid,
        }

    # ─────────────────────────────────────────────
    # Main loop: play N random tracks (or infinite)
    # ─────────────────────────────────────────────
    while True:
        if num_tracks != -1 and count >= num_tracks:
            break

        if skip_event.is_set():
            skip_event.clear()
            break

        res = await _play_one()
        if res:
            played.append(res)
            count += 1
            if res.get("skipped"):
                break

        await asyncio.sleep(0.3)

    return {"status": "ok", "language": lang, "played_count": len(played), "played": played}


# ─────────────────────────────────────────────
# Skip API
# ─────────────────────────────────────────────
@router.post("/skip-current-track")
async def skip_current_track():
    """Signal the playback loop to stop the current track immediately."""
    skip_event.set()
    return {"status": "skipping"}


# ─────────────────────────────────────────────
# Debug: show in-memory cache
# ─────────────────────────────────────────────
@router.get("/debug/loaded-tracks")
def debug_loaded_tracks():
    """Show count and sample of currently cached tracks."""
    if not current_decade_genre_tracks:
        return {"count": 0, "sample": []}
    return {
        "count": len(current_decade_genre_tracks),
        "sample": current_decade_genre_tracks[:3],
    }
