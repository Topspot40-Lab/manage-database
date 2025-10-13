# backend/routers/supabase_loader/play_random.py
from __future__ import annotations
import asyncio, logging
from typing import Literal
from fastapi import APIRouter, Query
from sqlmodel import Session as SQLSession
from sqlalchemy.exc import OperationalError, InterfaceError
from backend.database import engine
from backend.state import skip_event
from backend.utils.naming import normalize_language_code_canon
from backend.services.radio_pick import fetch_random_pick
from backend.config.volume import PLAY_FULL_TRACK
from backend.services.radio_runtime import (
    log_header_and_texts,
    build_intro_jobs,
    narration_keys_for,
    maybe_play_bed,
    play_narrations,
    play_track_with_skip,
)
from backend.services.supabase_loader_service import current_decade_genre_tracks


logger = logging.getLogger(__name__)
router = APIRouter(tags=["Supabase: Play Random"])


@router.get("/play-random-track-from-db")
async def play_random_track_from_db(
    play_intro: bool = Query(True, description="Play intro MP3(s) if available"),
    play_detail: bool = Query(True, description="Play detail MP3 if available"),
    play_artist_description: bool = Query(True, description="Play artist description MP3 if available"),
    play_track: bool = Query(True, description="Play the Spotify track"),
    num_tracks: int = Query(1, description="How many random tracks to play (-1 = keep playing forever)"),
    tts_language: Literal["en", "es", "ptbr", "pt-BR"] = Query("en"),
):
    """Pick random tracks from the DB and play them sequentially with narrations."""
    lang = normalize_language_code_canon(tts_language)
    played, count = [], 0

    async def _play_one() -> dict | None:
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
            logger.warning("No playable tracks found (need spotify_track_id != NULL).")
            return None

        track, artist, tr_rows = pick.track, pick.artist, pick.rankings
        log_header_and_texts(lang=lang, track=track, artist=artist, tr_rows=tr_rows)

        intro_jobs = build_intro_jobs(lang=lang, tr_rows=tr_rows) if play_intro else []
        detail_bucket, detail_key, artist_bucket, artist_key = narration_keys_for(lang=lang, track=track, artist=artist)

        # Narrations
        if (play_intro and intro_jobs) or (play_detail and detail_bucket and detail_key) or (
            play_artist_description and artist_bucket and artist_key
        ):
            await maybe_play_bed()

        await play_narrations(
            play_intro=play_intro,
            play_detail=play_detail,
            play_artist=play_artist_description,
            intro_jobs=intro_jobs,
            detail_bucket=detail_bucket,
            detail_key=detail_key,
            artist_bucket=artist_bucket,
            artist_key=artist_key,
        )

        # Track playback
        skipped_mid = False
        if play_track and track.spotify_track_id:
            try:
                skipped_mid = await play_track_with_skip(track=track, full_flag=PLAY_FULL_TRACK)
                if skipped_mid:
                    logger.info("⏭️ Skip triggered mid-track.")
            except Exception as e:
                logger.exception("Failed to play track: %s", e)

        return {
            "track": {"id": track.id, "name": track.track_name, "spotify_track_id": track.spotify_track_id},
            "artist": {"id": artist.id, "name": artist.artist_name, "spotify_artist_id": artist.spotify_artist_id},
            "skipped": skipped_mid,
        }

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


@router.post("/skip-current-track")
async def skip_current_track():
    """Signal the current track playback loop to stop immediately."""
    skip_event.set()
    return {"status": "skipping"}

# ─────────────────────────────────────────────────────────────
# Debug endpoint: check what’s loaded in memory
# ─────────────────────────────────────────────────────────────
@router.get("/debug/loaded-tracks")
def debug_loaded_tracks():
    """Show count and first few loaded tracks from in-memory cache."""
    if not current_decade_genre_tracks:
        return {"count": 0, "sample": []}
    return {
        "count": len(current_decade_genre_tracks),
        "sample": current_decade_genre_tracks[:3],
    }
