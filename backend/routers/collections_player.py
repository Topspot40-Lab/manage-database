# backend/routers/collection_player.py
from __future__ import annotations

import asyncio
import logging
import random
from typing import Literal
from fastapi import APIRouter, Query

from sqlmodel import select
from backend.database import get_db_session
from backend.models.dbmodels import (
    Track,
    Artist,
    Collection,
    CollectionTrackRanking,
)

# Playback controller
from backend.routers.playback_control import (
    start_new_sequence,
    cancel_current_sequence,
    _flags,
)

# Narration + playback services
from backend.services.radio_runtime import (
    _update_flags,
    _respect_user_controls,
    log_header_and_texts,
    build_intro_jobs,
    narration_keys_for,
    play_narrations,
)

from backend.services.spotify.playback import play_spotify_track
from backend.services.play_policy import compute_play_seconds, sleep_with_skip
from backend.state import skip_event

router = APIRouter(prefix="/supabase", tags=["Supabase: Collections"])

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# INTERNAL PLAYBACK LOOP
# ─────────────────────────────────────────────
async def _run_play_sequence_collection(
    *,
    collection_slug: str,
    start_rank: int,
    end_rank: int,
    mode: Literal["count_up", "count_down", "random"],
    tts_language: str,
    play_intro: bool,
    play_detail: bool,
    play_artist_description: bool,
    play_track: bool,
    text_intro: bool,
    text_detail: bool,
    text_artist_description: bool,
):
    """
    Full playback loop for Collection mode.
    """

    logger.info(
        f"🎧 COLLECTION START: {collection_slug} {start_rank}-{end_rank} mode={mode}"
    )

    # ───────────────────────────────────────
    # 1️⃣ Load collection tracks inside the task
    # ───────────────────────────────────────
    with get_db_session() as db:
        q = (
            select(Track, Artist, CollectionTrackRanking, Collection)
            .join(Artist, Artist.id == Track.artist_id)
            .join(CollectionTrackRanking, CollectionTrackRanking.track_id == Track.id)
            .join(Collection, Collection.id == CollectionTrackRanking.collection_id)
            .where(
                Collection.slug == collection_slug,
                CollectionTrackRanking.ranking >= start_rank,
                CollectionTrackRanking.ranking <= end_rank,
            )
        )

        rows = db.exec(q).all()

    if not rows:
        logger.warning(f"⚠️ No tracks found in collection: {collection_slug}")
        cancel_current_sequence()
        return

    # Apply ordering mode
    if mode == "count_up":
        rows.sort(key=lambda r: r[2].ranking)
    elif mode == "count_down":
        rows.sort(key=lambda r: r[2].ranking, reverse=True)
    elif mode == "random":
        random.shuffle(rows)

    # Update global state
    _flags.mode = "collection"
    _flags.context = {"collection_slug": collection_slug}

    # ───────────────────────────────────────
    # 2️⃣ RADIO PLAYBACK LOOP
    # ───────────────────────────────────────
    for track, artist, ctr_rank, coll in rows:
        rank = ctr_rank.ranking

        if _flags.cancel_requested:
            logger.info("🛑 Cancel flag detected — stopping collection playback.")
            break

        logger.info("──────────────────────────────────────────────")
        logger.info(f"▶ Rank #{rank:02d}: {track.track_name} — {artist.artist_name}")

        # Update flags for UI + TTS services
        _update_flags(
            phase="prelude",
            lang=tts_language,
            mode="collection",
            rank=rank,
            track_name=track.track_name,
            artist_name=artist.artist_name,
        )
        await _respect_user_controls()

        # ───────────────────────────────
        # Narration
        # ───────────────────────────────
        intro_text, detail_text, artist_text = log_header_and_texts(
            lang=tts_language,
            track=track,
            artist=artist,
            tr_rows=[(ctr_rank, coll.slug, "collection")],
        )

        intro_jobs = build_intro_jobs(
            lang=tts_language,
            tr_rows=[(ctr_rank, coll.slug, "collection")],
        )

        detail_bucket, detail_key, artist_bucket, artist_key = narration_keys_for(
            lang=tts_language,
            track=track,
            artist=artist,
        )

        await play_narrations(
            play_intro=play_intro,
            play_detail=play_detail,
            play_artist=play_artist_description,
            intro_jobs=intro_jobs,
            detail_bucket=detail_bucket,
            detail_key=detail_key,
            artist_bucket=artist_bucket,
            artist_key=artist_key,
            lang=tts_language,
            mode="collection",
            rank=rank,
            track_name=track.track_name,
            artist_name=artist.artist_name,
        )

        # ───────────────────────────────
        # Track playback
        # ───────────────────────────────
        if play_track and track.spotify_track_id:
            _update_flags(
                phase="track",
                lang=tts_language,
                mode="collection",
                rank=rank,
                track_name=track.track_name,
                artist_name=artist.artist_name,
            )
            await _respect_user_controls()

            logger.info(f"🎵 Playing {track.track_name} — rank {rank}")
            play_spotify_track(track.spotify_track_id)

            play_secs = compute_play_seconds(track)
            skipped = await sleep_with_skip(skip_event, play_secs)

            if skipped:
                logger.info("⏭️ Skip pressed — moving to next track.")
            else:
                logger.info("✅ Track finished normally.")

        await _respect_user_controls()
        await asyncio.sleep(0.5)

    # Wrap up
    cancel_current_sequence()
    logger.info("✅ Collection playback finished cleanly.")
    return


# ─────────────────────────────────────────────
# PUBLIC API: START COLLECTION PLAYBACK
# ─────────────────────────────────────────────
@router.get("/play-collection")
async def play_collection_sequence(
    collection_slug: str = Query(...),
    start_rank: int = Query(1),
    end_rank: int = Query(40),
    mode: Literal["count_up", "count_down", "random"] = Query("count_up"),
    tts_language: Literal["en", "es", "ptbr", "pt-BR"] = Query("en"),
    play_intro: bool = Query(True),
    play_detail: bool = Query(True),
    play_artist_description: bool = Query(True),
    play_track: bool = Query(False),
    text_intro: bool = Query(True),
    text_detail: bool = Query(False),
    text_artist_description: bool = Query(False),
):
    """
    Launches a new async playback sequence.
    Cancels any previous one automatically.
    """

    logger.info(
        f"▶ COLLECTION REQUEST: {collection_slug} {start_rank}-{end_rank} mode={mode}"
    )

    coro = _run_play_sequence_collection(
        collection_slug=collection_slug,
        start_rank=start_rank,
        end_rank=end_rank,
        mode=mode,
        tts_language=tts_language,
        play_intro=play_intro,
        play_detail=play_detail,
        play_artist_description=play_artist_description,
        play_track=play_track,
        text_intro=text_intro,
        text_detail=text_detail,
        text_artist_description=text_artist_description,
    )

    start_new_sequence(coro)

    return {
        "status": "started",
        "collection": collection_slug,
        "mode": mode,
        "range": [start_rank, end_rank],
    }
