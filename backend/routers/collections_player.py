# backend/routers/collection_player.py
from __future__ import annotations

import asyncio
import logging
import random
from typing import Literal

from fastapi import APIRouter, Query, Depends
from sqlmodel import select

from backend.database import get_db_session, get_db
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

# Narration + pipeline
from backend.services.radio_runtime import (
    log_header_and_texts,
    build_intro_jobs,
    narration_keys_for,
    play_narrations,
    _update_flags,
    _respect_user_controls,
)

# Unified Spotify player
from backend.services.playback_helpers import play_track_with_skip

router = APIRouter(prefix="/supabase", tags=["Supabase: Collections"])
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# INTERNAL BACKGROUND TASK
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
    Radio-style playback for Collections.
    Safe: Opens its own DB session inside the task.
    """

    logger.info(
        f"🎧 COLLECTION START: {collection_slug} {start_rank}-{end_rank} mode={mode}"
    )

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
        logger.warning(f"⚠️ No tracks found for collection: {collection_slug}")
        await cancel_current_sequence()
        return

    # Sorting mode
    if mode == "count_up":
        rows.sort(key=lambda r: r[2].ranking)
    elif mode == "count_down":
        rows.sort(key=lambda r: r[2].ranking, reverse=True)
    else:
        random.shuffle(rows)

    _flags.mode = "collection"
    _flags.context = {"collection_slug": collection_slug}

    # ─────────────────────────────────────────────
    # 2️⃣ Playback Loop
    # ─────────────────────────────────────────────
    for track, artist, ctr_rank, coll in rows:
        rank = ctr_rank.ranking

        # Cancel check
        if _flags.cancel_requested:
            logger.info("🛑 Cancel requested — stopping collection playback.")
            break

        logger.info("──────────────────────────────────────────────")
        logger.info(f"▶ Rank #{rank:02d}: {track.track_name} — {artist.artist_name}")

        _update_flags(
            phase="prelude",
            lang=tts_language,
            mode="collection",
            rank=rank,
            track_name=track.track_name,
            artist_name=artist.artist_name,
        )
        await _respect_user_controls()

        # ─────────────── Narration ────────────────
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
            lang=tts_language, track=track, artist=artist
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

        # ─────────────────────────────────────────────
        # Spotify Track Playback (Unified handler)
        # ─────────────────────────────────────────────
        if play_track:
            skipped = await play_track_with_skip(
                track,
                lang=tts_language,
                mode="collection",
                rank=rank,
                track_name=track.track_name,
                artist_name=artist.artist_name,
            )

        await _respect_user_controls()
        await asyncio.sleep(0.5)

    # Cleanup at end
    await cancel_current_sequence()
    logger.info("✅ Collection playback finished cleanly.")


# ─────────────────────────────────────────────
# PUBLIC — START PLAYBACK
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
    Launches background collection playback. Cancels any previous playback task.
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

    await start_new_sequence(coro)

    return {
        "status": "started",
        "collection": collection_slug,
        "mode": mode,
        "range": [start_rank, end_rank],
    }


# ─────────────────────────────────────────────
# PUBLIC — PREVIEW METADATA
# ─────────────────────────────────────────────
@router.get("/get-collection")
async def get_collection_metadata(
    collection_slug: str = Query(...),
    start_rank: int = Query(1),
    end_rank: int = Query(40),
    db = Depends(get_db),
):
    """
    Returns track metadata for Svelte preview in Car Mode.
    """

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
        .order_by(CollectionTrackRanking.ranking)
    )

    rows = db.exec(q).all()
    if not rows:
        return {"status": "empty", "tracks": []}

    tracks = []
    for track, artist, ctr_rank, coll in rows:
        tracks.append(
            {
                "rank": ctr_rank.ranking,
                "trackName": track.track_name,
                "artistName": artist.artist_name,
                "yearReleased": getattr(track, "year_released", None),
                "durationMs": getattr(track, "duration_ms", None),
                "albumArtwork": getattr(track, "album_artwork", None),
                "spotifyTrackId": getattr(track, "spotify_track_id", None),
                "albumName": getattr(track, "album_name", None),
            }
        )

    return {"status": "ok", "total": len(tracks), "tracks": tracks}
